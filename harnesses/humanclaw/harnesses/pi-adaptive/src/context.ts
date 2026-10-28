import type { AgentMessage } from "@earendil-works/pi-agent-core";

export type Audit = (event: string, data: unknown) => void;
export interface Profile {
  version: string; pi_version: string; base_effort: "medium"; high_effort: "high";
  recent_exchanges: number; trim_at_exchanges: number;
  model_capabilities: { model: string; max_images: number; max_input_tokens: number; image_token_reserve: number };
}
export function publicState(message: AgentMessage): Record<string, any> | undefined {
  if (message.role !== "toolResult") return;
  for (const block of message.content) if (block.type === "text") {
    try { const p = JSON.parse(block.text); if (p.state && "current_observation" in p.state) return p.state; } catch { /* plain text */ }
  }
}
export function assertPaired(messages: AgentMessage[]): void {
  const pending = new Set<string>();
  for (const m of messages) {
    if (m.role === "assistant") for (const b of m.content) if (b.type === "toolCall") pending.add(b.id);
    if (m.role === "toolResult" && !pending.delete(m.toolCallId)) throw new Error("Unpaired tool result");
  }
  if (pending.size) throw new Error("Unpaired tool call");
}
export function observationIds(message: AgentMessage): string[] {
  if (message.role !== "toolResult") return [];
  for (const b of message.content) if (b.type === "text") {
    try { const p = JSON.parse(b.text); return [...(p.value?.result?.observations ?? p.value?.observations ?? []).map((o: any) => o.id), ...(p.value?.records ?? []).map((o: any) => o.id), ...(p.value?.result?.evidence_references ?? [])]; }
    catch { /* Nonstructured tool result */ }
  }
  return [];
}
export function cost(messages: AgentMessage[], reserve: number): { tokens: number; images: number } {
  let images = 0;
  // SDK 1.3 carries system prompt AND tool schemas in system messages.
  const text = JSON.stringify(messages, (_key, value) => {
    if (value?.type === "image") { images++; return { type: "image" }; }
    return value;
  });
  return { tokens: Buffer.byteLength(text) + images * reserve + 1024, images };
}

/** Whole exchanges; immutable assistant reasoning/signatures. No universal image rule. */
export class ContextBuilder {
  floor = 0;
  profile: Profile;
  audit: Audit;
  constructor(profile: Profile, audit: Audit) { this.profile = profile; this.audit = audit; }
  project(messages: AgentMessage[]): AgentMessage[] {
    const p = this.profile, systems = messages.filter(m => m.role === "system");
    const first = messages.findIndex(m => m.role === "user");
    if (first < 0) throw new Error("Original task missing");
    const groups: AgentMessage[][] = [];
    for (const message of messages.slice(first + 1)) {
      if (message.role === "system") continue;
      if (message.role === "assistant" || !groups.length) groups.push([]);
      groups.at(-1)!.push(message);
    }
    const state = [...messages].reverse().map(publicState).find(Boolean);
    // Latest observation exchange must survive subsequent memory/computation tools.
    const current = state?.current_observation;
    let observationGroup = -1;
    let discoveryGroup = -1;
    const pins: string[] = state?.pinned_evidence ?? [];
    const pinnedGroups = new Set<number>();
    groups.forEach((g, i) => {
      if (g.some(m => observationIds(m).includes(current))) observationGroup = i;
      if (state?.adaptation?.pending && g.some(m => m.role === "toolResult" && m.toolName === "adaptive__discover" && !m.isError)) discoveryGroup = i;
      if (g.some(m => observationIds(m).some(id => pins.includes(id)))) pinnedGroups.add(i);
    });
    if (groups.length - this.floor > p.trim_at_exchanges) this.floor = Math.max(0, groups.length - p.recent_exchanges);
    let selected = groups.map((g, i) => ({ g, i })).filter(({ i }) => i >= this.floor || i === observationGroup || i === discoveryGroup || pinnedGroups.has(i));
    const initial = messages[first];
    let keepInitialImage = observationGroup < 0;
    const build = (): AgentMessage[] => {
      const task = !keepInitialImage && initial.role === "user" && Array.isArray(initial.content)
        ? { ...initial, content: initial.content.filter(b => b.type !== "image") } : initial;
      return [...systems, task, ...selected.flatMap(({g}) => g), ...(state ? [{role: "user" as const,
        content: `Durable task memory (model interpretations retain provenance): ${JSON.stringify(state)}`, timestamp: 0}] : [])];
    };
    let result = build();
    while (true) {
      const c = cost(result, p.model_capabilities.image_token_reserve);
      if (c.images <= p.model_capabilities.max_images && c.tokens <= p.model_capabilities.max_input_tokens) break;
      let removable = selected.findIndex(({i}) => i !== observationGroup && i !== discoveryGroup && i !== groups.length - 1 && !pinnedGroups.has(i));
      if (removable < 0) removable = selected.findIndex(({i}) => i !== observationGroup && i !== discoveryGroup && i !== groups.length - 1);
      if (removable < 0) throw new Error("Context overflow: task, schemas, current evidence and latest exchange cannot fit");
      selected.splice(removable, 1);
      result = build();
    }
    assertPaired(result);
    this.audit("context", { current_observation: current, discovery_exchange: discoveryGroup, kept_exchanges: selected.map(x => x.i),
      original_exchanges: groups.length, schemas_included: true, ...cost(result, p.model_capabilities.image_token_reserve) });
    return result;
  }
}
