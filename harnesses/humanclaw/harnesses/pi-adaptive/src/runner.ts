import { readFileSync } from "node:fs";
import { join } from "node:path";
import { createInterface } from "node:readline";
import { createAgentSession, DefaultResourceLoader, ModelRuntime, SessionManager, SettingsManager } from "@earendil-works/pi-coding-agent";
import { McpClient, StreamableHttpTransport } from "@earendil-works/pi-mcp";
import { Type } from "typebox";
import { toLlmContent } from "@earendil-works/pi-mcp";
import { createHash } from "node:crypto";
import { ContextBuilder, publicState, type Profile, type Audit } from "./context.ts";
import { ExecutionBoundary } from "./execution-boundary.ts";
import { adaptationContext } from "./adaptation.ts";

const output = (value: unknown) => process.stdout.write(JSON.stringify(value) + "\n");

async function main(): Promise<void> {
  const configPath = process.env.PI_ADAPTIVE_CONFIG;
  if (!configPath) throw new Error("Missing PI_ADAPTIVE_CONFIG");
  const config = JSON.parse(readFileSync(configPath, "utf8")) as {
    profile: Profile; agent_dir: string; session_dir: string; model: string;
    max_actions: number; instruction: string; connection: string;
  };
  const { profile } = config;
  if (profile.version !== "pi-adaptive-v1" || profile.pi_version !== "1.3.0"
    || profile.model_capabilities.model !== config.model) throw new Error("Unsupported or mismatched adaptive profile");
  const mcp = JSON.parse(readFileSync(join(config.agent_dir, "mcp.json"), "utf8")).mcpServers[config.connection];
  const client = new McpClient({ name: "pi-adaptive", version: "0.1.0", requestTimeoutMs: mcp.timeout });
  await client.connect(new StreamableHttpTransport({ url: mcp.url, headers: mcp.headers, openGetStream: false }));
  const definitions = await client.listTools();
  const prompt = readFileSync(new URL("../prompts/adaptive.md", import.meta.url), "utf8");
  const settingsManager = SettingsManager.create(process.cwd(), config.agent_dir);
  const resourceLoader = new DefaultResourceLoader({
    cwd: process.cwd(), agentDir: config.agent_dir, settingsManager,
    noExtensions: true, disabledBuiltinExtensions: ["mcp", "codemode", "tool-search"],
    noSkills: true, noPromptTemplates: true, noThemes: true, noContextFiles: true,
    extensionFactories: [pi => { pi.on("before_agent_start", async () => ({ systemPrompt: prompt })); }],
  });
  await resourceLoader.reload();
  const modelRuntime = await ModelRuntime.create({ authPath: join(config.agent_dir, "auth.json"),
    modelsPath: join(config.agent_dir, "models.json"), allowModelNetwork: false });
  const model = modelRuntime.getModel("humanclaw", config.model);
  if (!model) throw new Error(`Configured model ${config.model} is unavailable`);
  const { session } = await createAgentSession({
    cwd: process.cwd(), agentDir: config.agent_dir, modelRuntime, model, resourceLoader, settingsManager,
    thinkingLevel: profile.base_effort, tools: ["adaptive__*"],
    customTools: definitions.map(tool => ({name: `adaptive__${tool.name}`, label: tool.name,
      description: tool.description ?? tool.name, parameters: Type.Unsafe(tool.inputSchema),
      executionMode: "sequential" as const,
      async execute(_id, args, signal) {
        const result = await client.callTool(tool.name, args as Record<string, unknown>, {signal});
        return {content: toLlmContent(result), isError: result.isError === true, details: {}};
      }})),
    sessionManager: SessionManager.create(process.cwd(), config.session_dir),
  });
  const audit: Audit = (event, data) => {
    session.sessionManager.appendCustomEntry(`humanclaw.${event}`, data);
    output({ type: "humanclaw_policy", event, data });
  };
  const builder = new ContextBuilder(profile, audit);
  const agent = session.agent;
  agent.toolExecution = "sequential";
  const registry = [...agent.state.tools];
  const nextWithContext = agent.prepareNextTurnWithContext;
  const next = agent.prepareNextTurn;
  agent.prepareNextTurnWithContext = async (turn, signal) => {
    const previous = nextWithContext ? await nextWithContext(turn, signal) : await next?.(signal);
    const context = adaptationContext(previous?.context ?? turn.context, registry);
    // The SDK rebuilds request contexts and retries from agent.state.tools.
    agent.state.tools = context.tools ?? [];
    return {...previous, context};
  };
  const boundary = new ExecutionBoundary();
  const before = agent.beforeToolCall;
  agent.beforeToolCall = async (context, signal) => {
    const previous = await before?.(context, signal);
    if (previous?.block) return previous;
    const reason = boundary.admit(context.assistantMessage, context.toolCall.name, context.args);
    if (reason) audit("execution_boundary", {tool: context.toolCall.name, reason});
    return reason ? {...previous, block: true, reason} : previous;
  };
  const transform = agent.transformContext;
  agent.transformContext = async (messages, signal) => builder.project(transform ? await transform(messages, signal) : messages);
  const prepare = agent.prepareRequest;
  const decisions = new Map<string, "medium" | "high">();
  agent.prepareRequest = async (request, signal) => {
    const previous = await prepare?.(request, signal);
    const context = previous?.context ?? request.context;
    const stable = context.messages.filter(m => m.role !== "assistant" || !["error", "aborted"].includes(m.stopReason));
    const key = createHash("sha256").update(JSON.stringify(stable)).digest("hex");
    const state = [...context.messages].reverse().map(publicState).find(Boolean);
    const effort = decisions.get(key) ?? (state?.recommendation?.effort === "high" ? "high" : "medium");
    decisions.set(key, effort);
    audit("decision", {id: key, effort, memory_version: state?.memory_version, policy_version: state?.policy_version,
      reason: state?.feedback ?? "startup_discovery"});
    return {...previous, context, thinkingLevel: effort};
  };
  session.setAutoCompactionEnabled(false);
  audit("profile", {profile, image_budget_owner: "context_builder"});
  session.subscribe(event => {
    // Keep native lifecycle/settlement events; streaming deltas need no full growing message copy.
    if (event.type !== "message_update") output(event);
  });
  output({ type: "humanclaw_ready" });
  // HumanCLAW's adapter needs prompt + response + native events/agent_settled, not the full CLI RPC UI.
  // Do not call runRpcMode with a bare AgentSession (it requires AgentSessionRuntime).
  let prompted = false;
  const lines = createInterface({ input: process.stdin, crlfDelay: Infinity });
  for await (const line of lines) {
    let command: { id?: string; type?: string; message?: string; images?: never[] } = {};
    try {
      command = JSON.parse(line);
      if (command.type !== "prompt" || prompted || typeof command.message !== "string")
        throw new Error("This isolated runner accepts exactly one episode prompt");
      prompted = true;
      output({ id: command.id, type: "response", command: "prompt", success: true });
      await session.prompt(command.message, { images: command.images, source: "rpc", expandPromptTemplates: false });
    } catch (error) {
      output({ id: command.id, type: "response", command: command.type ?? "prompt", success: false,
        error: error instanceof Error ? error.message : String(error) });
    }
  }
  await client.close();
  session.dispose();
}

main().catch(error => {
  output({ type: "response", command: "startup", success: false, error: String(error) });
  process.exitCode = 1;
});
