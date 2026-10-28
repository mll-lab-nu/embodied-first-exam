import type { AgentContext, AgentTool } from "@earendil-works/pi-agent-core";
import { publicState } from "./context.ts";

/** Advertise the host's legal lifecycle transitions before the SDK declares tools.
 * Keep the complete registry outside the filtered context so tools return after
 * validation, activation, discard or a fresh environment observation.
 */
export function adaptationContext(context: AgentContext, registry: AgentTool<any>[]): AgentContext {
  const state = [...context.messages].reverse().map(publicState).find(Boolean);
  const available = state?.adaptation?.available_tools;
  if (!Array.isArray(available)) return {...context, tools: registry};
  const allowed = new Set(available.map(name => `adaptive__${name}`));
  const tools = registry.filter(tool => !tool.name.startsWith("adaptive__") || allowed.has(tool.name)).map(tool => {
    if (tool.name === "adaptive__adapter" && state?.interface?.available_actions) {
      return {...tool, parameters: {...tool.parameters, properties: {...tool.parameters.properties,
        action: {type: "string", enum: state.interface.available_actions},
      }}};
    }
    if (tool.name !== "adaptive__candidate") return tool;
    const pending = state?.adaptation?.pending;
    return {...tool, parameters: {...tool.parameters, properties: {...tool.parameters.properties,
      protocol: {type: "string", enum: state!.adaptation.available_protocols},
      ...(pending ? {parent: {type: "string", const: pending.candidate_id}} : {}),
    }}};
  });
  return {...context, tools};
}
