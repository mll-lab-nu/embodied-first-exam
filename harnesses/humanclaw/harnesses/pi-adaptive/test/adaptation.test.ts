import test from "node:test";
import assert from "node:assert/strict";
import type { AgentContext, AgentTool } from "@earendil-works/pi-agent-core";
import { adaptationContext } from "../src/adaptation.ts";
import { ContextBuilder, type Profile } from "../src/context.ts";
import { publicState } from "../src/context.ts";

const names = ["discover", "candidate", "validate", "activate", "discard", "execute", "receipt", "memory", "evidence", "compute"];
const registry = names.map(name => ({name: `adaptive__${name}`, parameters: {type: "object", properties: {
  protocol: {type: "string"}, parent: {type: ["string", "null"]},
}}})) as AgentTool<any>[];
function context(available: string[], pending?: object, protocols = ["feedback-policy-v1"]): AgentContext {
  return {messages: [{role: "toolResult", toolCallId: "proposal", toolName: "adaptive__candidate", timestamp: 0, isError: false,
    content: [{type: "text", text: JSON.stringify({state: {current_observation: "o54", adaptation: {
      available_tools: available, available_protocols: protocols, pending,
    }}})}]}]};
}

test("pending candidate hides discovery/proposals and exposes validation or explicit exit", () => {
  const original = JSON.stringify(registry);
  const pending = {candidate_id: "pending-54", status: "unvalidated", next_action: "validate"};
  const next = adaptationContext(context(["validate", "discard", "execute", "receipt", "memory", "evidence"], pending), registry);
  assert.deepEqual(next.tools!.map(t => t.name).sort(),
    ["validate", "discard", "execute", "receipt", "memory", "evidence"].map(n => `adaptive__${n}`).sort());
  assert.equal(JSON.stringify(registry), original);
});

test("failed validation exposes only a child repair; activation and fresh evidence restore tools", () => {
  const failed = adaptationContext(context(["candidate", "discard", "execute", "receipt"], {candidate_id: "failed-54"}), registry);
  const candidate = failed.tools!.find(t => t.name === "adaptive__candidate")!;
  assert.deepEqual(candidate.parameters.properties.protocol.enum, ["feedback-policy-v1"]);
  assert.equal(candidate.parameters.properties.parent.const, "failed-54");
  const passed = adaptationContext(context(["activate", "discard", "execute", "receipt"], {candidate_id: "fixed-54"}), registry);
  assert.ok(passed.tools!.some(t => t.name === "adaptive__activate"));
  assert.ok(!passed.tools!.some(t => t.name === "adaptive__validate" || t.name === "adaptive__candidate"));
  const closed = adaptationContext(context(["discover", "candidate", "execute", "receipt"], undefined, ["angle-delta-v1"]), registry);
  assert.deepEqual(closed.tools!.find(t => t.name === "adaptive__candidate")!.parameters.properties.protocol.enum, ["angle-delta-v1"]);
  const fresh = adaptationContext(context(names), registry);
  assert.equal(fresh.tools!.length, registry.length);
  assert.deepEqual(fresh.tools!.find(t => t.name === "adaptive__candidate")!.parameters.properties.parent.type, ["string", "null"]);
});

test("context trimming preserves the host-owned candidate and next transition", () => {
  const pending = {candidate_id: "pending-54", status: "unvalidated", next_action: "validate",
    candidate: {implementation: {recovery_note: "Reobserve before moving"}}};
  const messages: AgentContext["messages"] = [
    {role: "system", content: "instructions", timestamp: 0}, {role: "user", content: "task", timestamp: 0},
  ];
  for (let i = 0; i < 20; i++) {
    const toolName = i === 0 ? "adaptive__discover" : "adaptive__memory";
    messages.push({role: "assistant", content: [{type: "toolCall", id: `call-${i}`, name: toolName, arguments: {}}],
      stopReason: "toolUse", timestamp: i} as any);
    messages.push({...context(["validate", "discard", "execute"], pending).messages[0], toolName, toolCallId: `call-${i}`} as any);
  }
  const profile: Profile = {version: "pi-adaptive-v1", pi_version: "1.3.0", base_effort: "medium", high_effort: "high",
    recent_exchanges: 2, trim_at_exchanges: 4,
    model_capabilities: {model: "test", max_images: 3, max_input_tokens: 30000, image_token_reserve: 1000}};
  const projected = new ContextBuilder(profile, () => {}).project(messages);
  const durable = projected.at(-1);
  assert.equal(durable?.role, "user");
  assert.match(JSON.stringify(durable), /pending-54/);
  assert.match(JSON.stringify(durable), /Reobserve before moving/);
  assert.match(JSON.stringify(durable), /validate/);
  assert.ok(projected.some(m => m.role === "toolResult" && m.toolName === "adaptive__discover"));
  assert.ok(projected.length < messages.length);
});

test("bootstrap state and interface repair survive without any observation", () => {
  const message = {role: "toolResult", toolCallId: "discovery", toolName: "adaptive__discover", timestamp: 0,
    content: [{type: "text", text: JSON.stringify({state: {current_observation: null, policy_version: "p1",
      adaptation: {available_tools: ["discover", "adapter", "workspace", "memory"], available_protocols: []},
      interface: {pending: {id: "binding-1", artifact: {source: "public client codec"}}, available_actions: ["validate", "discard"]},
    }})}]} as any;
  assert.equal(publicState(message)?.current_observation, null);
  const tools = [...registry, {name: "adaptive__adapter", parameters: {type: "object", properties: {action: {type: "string"}}}}] as AgentTool<any>[];
  const projected = adaptationContext({messages: [message]}, tools);
  assert.deepEqual(projected.tools!.find(t => t.name === "adaptive__adapter")!.parameters.properties.action.enum, ["validate", "discard"]);
  assert.ok(!projected.tools!.some(t => t.name === "adaptive__candidate"));
});
