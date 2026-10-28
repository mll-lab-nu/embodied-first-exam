# Audited source excerpts

These are documentation excerpts, not modified or executable source files. Line numbers refer to the pinned files listed below. Full-file hashes support matching these anchors to the reviewed snapshot. Native releases explain mechanisms but are not a proof of bit-identical builds of the recorded binary/package.

<a id="hc1"></a>

## HC1: src/humanclaw_bench/harnesses/environment.py

Snapshot: `humanclaw-r2`. SHA256: `b7d6d6c72b863f983f4676d362e842b671e1199b248eda32f4add8c26ed797d6`.

```text

   27 # Bump it with any change to that text. Runs that record no protocol used v1:
   28 # no Sit-duration fact, and Stop read "finish at the current pose; no generated motion".
   29 NATIVE_ACTION_PROTOCOL = "native-actions-v2"
   30
   31 # One generated motion chunk is 15 frames (n_future) played at 30 fps: 0.5 s.
   32 ACTION_NAMES = (
   33     "Walk<forward><slow|normal|fast> (0.2/0.4/0.6 metres)",
   34     "Stop/Stand (submits the current pose as the final pose and ends the episode; "
   35     "no further motion is generated)",
   36     "Turn<left|right><degrees> (clamped to 10–120 degrees)",
   37     "Climb upstairs<normal>",
   38     "Sit down<height> (height clamped to 0.15–0.85 metres; one call moves for only "
   39     "about 0.5 s and may not complete sitting down)",
   40     "Step back<distance> (clamped to 0.10–0.60 metres)",
   41     "Side step<left|right><distance> (clamped to 0.10–0.50 metres)",
   42     "Walk downstairs<normal>",
   43 )
   44
   45
   46 def tool_definitions() -> list[dict[str, Any]]:
   47     """Describe the eight public benchmark actions without private evaluator state."""
   48     return [{
   49         "name": name,
   50         "description": f"Execute one HumanCLAW action: {ACTION_NAMES[index]}. "
   51         "Use the latest observation_id. Describe the CURRENT image in visible_state, "
   52         "including whether the task target is visible. Return includes a new image. "
   53         "Call actions sequentially; reuse request_id only when retrying the same action.",
   54         "inputSchema": {
   55             "type": "object", "additionalProperties": False,
   56             "properties": {
   57                 "request_id": {"type": "string", "minLength": 1},
   58                 "observation_id": {"type": "integer", "minimum": 0},
   59                 "action_name": {"type": "string", "description": ACTION_NAMES[index]},
   60                 "visible_state": {"type": "string", "minLength": 1},
   61             },
   62             "required": ["request_id", "observation_id", "action_name", "visible_state"],
   63         },
   64         "annotations": {"readOnlyHint": False, "destructiveHint": False,
   65                         "idempotentHint": True, "openWorldHint": False},
   66     } for index, name in enumerate(SKILLS)]

```

```text

  103         """Describe the task and action protocol without adding a second planner.
  104
  105         Each native session requests this prompt once, so the protocol identity
  106         is recorded here, inside the session's trace.
  107         """
  108         event("environment.protocol", kind="environment", name="environment.protocol",
  109               data=protocol_identity())
  110         return (
  111             f"Perform this HumanCLAW embodied task: {self.instruction}\n"
  112             f"Current observation_id: 0. Maximum environment actions: {self.max_steps}.\n"
  113             "The attached image is the current first-person observation. Use the eight "
  114             "humanclaw environment tools to act. Each tool executes exactly one action "
  115             "and returns the next image and observation_id. Use a new request_id for "
  116             "each new action. Wait for its result before choosing another action. "
  117             "In visible_state describe the CURRENT image, whether the task target is "
  118             "visible and whether the near-body lane is clear. Do not claim hidden state. "
  119             "Use stand (Stop/Stand) when finished. When done is true, provide a short "
  120             "final answer and make no further environment calls."
  121         )
  122
  123     def submit(self, name: str, arguments: dict[str, Any]) -> Future:

```

```text

  157             raise RuntimeError("Environment actions must run on the simulator thread")
  158         request_id = args.get("request_id") if isinstance(args, dict) else None
  159         from_provider = isinstance(request_id, str) and (name, request_id) in self.provider_requests
  160         event("mcp.requested" if from_provider else "tool.requested", kind="tool", name=name,
  161               data={"arguments": args, "interface": "mcp"}, step=self.step)
  162         try:
  163             if name not in SKILLS or not isinstance(args, dict):
  164                 raise ValueError("Unknown action or invalid arguments")
  165             if set(args) != {"request_id", "observation_id", "action_name", "visible_state"}:
  166                 raise ValueError("Expected request_id, observation_id, action_name and visible_state")
  167             if any(not isinstance(args[k], str) or not args[k].strip()
  168                    for k in ("request_id", "action_name", "visible_state")):
  169                 raise ValueError("request_id, action_name and visible_state must be nonempty strings")
  170             fingerprint = json.dumps([name, args], sort_keys=True)
  171             if request_id in self.cache:
  172                 previous, result = self.cache[request_id]
  173                 if previous != fingerprint:
  174                     raise ValueError("request_id was already used with different arguments")
  175                 event("tool.deduplicated", kind="tool", name=name,
  176                       data={"request_id": request_id}, step=self.step)
  177                 return result
  178             if type(args["observation_id"]) is not int or args["observation_id"] != self.step:
  179                 raise ValueError(f"Stale observation: current observation_id is {self.step}")
  180             if self.done or self.failure is not None:
  181                 raise ValueError("Episode has ended; no further actions are allowed")
  182         except ValueError as exc:
  183             event("tool.rejected", kind="tool", name=name,
  184                   data={"error": str(exc), "request_id": request_id}, step=self.step)
  185             return {"isError": True, "content": [{"type": "text", "text": str(exc)}]}
  186
  187         plan = {"action_id": SKILLS.index(name), "action_name": args["action_name"],
  188                 "visible_state": args["visible_state"], "request_id": request_id,
  189                 "observation_id": self.step,
  190                 "native_call_ids": self.provider_requests.get((name, request_id), [])}
  191         with span("action.normalize", input=plan, step=self.step) as normal:
  192             action = normalize_action(plan)
  193             normal.set_output(action.to_json())
  194         decision = PlannerResult(raw_plan=plan, action=action, planner_skill=plan, verifier={})
  195         try:
  196             # The evaluator owns the sole tool execution span and metrics/physics.
  197             self.image, env_done = self.execute(self.step, decision)
  198         except BaseException as exc:
  199             # An uncertain partial execution is terminal, never automatically retried.
  200             self.failure = exc
  201             raise
  202         self.step += 1
  203         self.done = env_done or name == "stand" or self.step >= self.max_steps
  204         self.termination = ("stop" if name == "stand" else "environment_done" if env_done
  205                             else "max_steps" if self.done else "running")
  206         public = {"request_id": request_id, "observation_id": self.step,
  207                   "action": action.to_json(), "done": self.done,
  208                   "termination_reason": self.termination if self.done else None}
  209         result = {"isError": False, "content": [
  210             {"type": "text", "text": json.dumps(public)}, image_content(self.image),
  211         ]}
  212         self.cache[request_id] = fingerprint, result
  213         event("observation.available", kind="environment", name="environment.observation",
  214               data={**public, "image": self.image}, step=self.step)
  215         return result

```

<a id="hc2"></a>

## HC2: src/humanclaw_bench/harnesses/runtime.py

Snapshot: `humanclaw-r2`. SHA256: `d62984b6b457c4ba7b59aea8f74a941debc2bf3b7f0bf28fa9cbe14897c48bbb`.

```text

   69     value = json.loads(Path(path).expanduser().read_text())
   70     if not isinstance(value, dict):
   71         raise ValueError("Harness config must be a JSON object")
   72     allowed = {"codex_command", "codex_source", "pi_source", "pi_command", "node_command",
   73                "responses_base_url", "responses_base_url_env", "allow_http", "api_key_env", "auth", "timeout_seconds",
   74                "request_timeout_seconds", "startup_timeout_seconds", "context_window", "reasoning_effort",
   75                "max_images_per_request", *REAL_PROGRAM_KEYS}
   76     unknown = set(value) - allowed
   77     if unknown:
   78         raise ValueError(f"Unknown harness settings: {sorted(unknown)}; use api_key_env for credentials")
   79     for key in REAL_PROGRAM_KEYS:
   80         if key in value and (not isinstance(value[key], str) or not value[key].strip()):

```

```text

  410                     self._codex_config(home, services, env)
  411                 else:
  412                     self._pi_config(home, services, env)
  413                     command += ["--mode", "rpc", "--provider", "humanclaw", "--model", self.model_config["model"],
  414                                 "--session-dir", str(directory / "sessions"),
  415                                 "--thinking", self.config.get("reasoning_effort", "medium")]
  416                 events = NativeEvents(self.harness, services.call_names, services.requested_calls)
  417                 process = JsonProcess(command, workspace, env, events)
  418                 deadline = time.monotonic() + float(self.config.get("timeout_seconds", 3600))

```

```text

  468     def _pi_config(self, home, services, env):
  469         """Configure Pi models and direct MCP tools in a fresh agent directory."""
  470         agent = home / ".pi" / "agent"
  471         agent.mkdir(parents=True)
  472         env["PI_CODING_AGENT_DIR"] = str(agent)
  473         model = {"id": self.model_config["model"], "input": ["text", "image"], "reasoning": True,
  474                  "thinkingLevelMap": pi_thinking_level_map(self.model_config),
  475                  "contextWindow": int(self.config.get("context_window", 131072)),
  476                  "maxTokens": int(self.model_config.get("max_tokens", 8192))}
  477         (agent / "models.json").write_text(json.dumps({"providers": {"humanclaw": {
  478             "api": "openai-responses", "baseUrl": services.url + "/v1", "apiKey": services.bearer,
  479             "models": [model]}}}))
  480         (agent / "mcp.json").write_text(json.dumps({"mcpServers": {"humanclaw": {
  481             "url": services.url + "/mcp", "headers": {"Authorization": "Bearer " + services.bearer},
  482             "exposure": "direct", "timeout": 1200000}}}))
  483
  484     def _codex(self, process, services, bridge, deadline):
  485         """Initialize App Server, start one thread and wait for turn completion."""
  486         counter = 0
  487
  488         def request(method, params):
  489             """Match an App Server request ID while retaining intervening notifications."""
  490             nonlocal counter
  491             counter += 1
  492             ident = counter

```

```text

  542         """Start a Pi RPC prompt and wait past retries for agent_settled."""
  543         process.send({"id": "episode", "type": "prompt", "message": bridge.initial_prompt(),
  544                       "images": [image_content(bridge.image)]})
  545         failed_message = None
  546         while True:
  547             row = process.poll(bridge, deadline)
  548             if row is None:
  549                 continue
  550             if row.get("type") == "response" and row.get("success") is False:
  551                 raise RuntimeError(f"Pi rejected request: {row.get('error')}")
  552             if row.get("type") == "message_end":
  553                 message = row.get("message", {})
  554                 if message.get("role") == "assistant":
  555                     failed_message = message.get("errorMessage") if message.get("stopReason") in {"error", "aborted"} else None
  556             if row.get("type") == "agent_settled":
  557                 if row.get("aborted") or failed_message:
  558                     raise RuntimeError(f"Pi episode failed: {failed_message or 'aborted'}")
  559                 return
  560

```

<a id="hc3"></a>

## HC3: src/humanclaw_bench/harnesses/services.py

Snapshot: `humanclaw-r2`. SHA256: `4a54e34181e8d08b9e65ed49f740bd76c0cc73de61feb7da23d7cdbc6e476217`.

```text

   49 def cap_images(items, limit: int):
   50     """Fit a Responses input under a per-request image limit.
   51
   52     Keeps the first image (the task's initial observation) and the most recent ones; each older
   53     image is replaced in place by a short text note so the turn structure is unchanged.
   54     Returns the (copied) input and the number of images replaced.
   55     """
   56     if not isinstance(items, list) or limit < 2:
   57         return items, 0
   58     paths = []
   59
   60     def walk(value, path):
   61         """Collect the path of every input_image block below value."""
   62         if isinstance(value, dict):
   63             if value.get("type") == "input_image":
   64                 paths.append(path)
   65                 return
   66             for key, child in value.items():
   67                 walk(child, path + (key,))
   68         elif isinstance(value, list):
   69             for index, child in enumerate(value):
   70                 walk(child, path + (index,))
   71
   72     walk(items, ())
   73     excess = len(paths) - limit
   74     if excess <= 0:
   75         return items, 0
   76     items = copy.deepcopy(items)
   77     for path in paths[1:1 + excess]:
   78         parent = items
   79         for key in path[:-1]:
   80             parent = parent[key]
   81         parent[path[-1]] = {"type": "input_text", "text": IMAGE_OMITTED.format(limit=limit)}
   82     return items, excess
   83
   84

```

```text

  224         else:
  225             result = None
  226             error = {"code": -32601, "message": "Method not found"}
  227         handler.send_json(200, {"jsonrpc": "2.0", "id": ident,
  228                                **({"error": error} if error else {"result": result})})
  229
  230     def responses(self, handler, payload):
  231         """Record each HTTP attempt, forward its stream and retain raw usage."""
  232         native_payload = payload
  233         payload = dict(payload)
  234         if self.model_options.get("send_max_tokens") is False:
  235             payload.pop("max_output_tokens", None)
  236         elif self.model_options.get("max_tokens"):
  237             limit = int(self.model_options["max_tokens"])
  238             payload["max_output_tokens"] = min(limit, int(payload.get("max_output_tokens") or limit))
  239         if self.model_options.get("send_temperature") is False:
  240             payload.pop("temperature", None)
  241         elif "temperature" in self.model_options:
  242             payload["temperature"] = self.model_options["temperature"]
  243         images_dropped = 0
  244         if self.max_images:
  245             payload["input"], images_dropped = cap_images(payload.get("input"), int(self.max_images))
  246         with self._lock:
  247             self.calls += 1
  248             index = self.calls
  249             self.usage.append({})
  250         with span("model.responses", kind="model", input=trace_payload(payload), attributes={
  251             "model": payload.get("model"), "boundary": "provider_http_request",
  252             "transport": "responses", "request_index": index,

```

<a id="hc4"></a>

## HC4: src/humanclaw_bench/agent/skills.py

Snapshot: `humanclaw-r2`. SHA256: `2c46901ca65d31d13d8e6453ceabaa2e3da25e200f67cba61368db89473fa5be`.

```text

   89     tokens = [token.strip().lower().replace(" ", "_") for token in re.findall(r"<([^>]+)>", action_name)]
   90     if family_id == 0:
   91         speed = tokens[1] if len(tokens) >= 2 else "slow"
   92         speed = {"slow": "slow", "normal": "normal", "fast": "fast"}.get(
   93             speed,
   94             "slow",
   95         )
   96         distance = {"slow": 0.2, "normal": 0.4, "fast": 0.6}[speed]
   97         return SkillCall(
   98             skill="walk_forward",
   99             cond=[0.0, distance, 0.0],
  100             action_name=f"Walk<forward><{speed}>",
  101         )
  102
  103     if family_id == 2:
  104         direction = tokens[0] if len(tokens) >= 1 else "left"
  105         direction = "right" if direction == "right" else "left"
  106         degree_text = tokens[1] if len(tokens) >= 2 else action_name
  107         match = re.search(r"-?\d+(?:\.\d+)?", degree_text)
  108         degree = max(10.0, min(120.0, float(match.group(0)))) if match else 10.0
  109         signed_degree = degree if direction == "left" else -degree
  110         degree_label = str(int(round(degree)))
  111         return SkillCall(
  112             skill="turn",
  113             cond=signed_degree,
  114             action_name=f"Turn<{direction}><{degree_label}>",
  115         )
  116
  117     if family_id == 3:
  118         return SkillCall(
  119             skill="step_climb_up",
  120             cond=[0.28, 0.30],
  121             action_name="Climb upstairs<normal>",
  122         )
  123
  124     if family_id == 4:
  125         match = re.search(r"\d+(?:\.\d+)?", action_name)
  126         target_height = float(match.group(0)) if match else 0.50
  127         target_height = max(0.15, min(0.85, target_height))
  128         return SkillCall(
  129             skill="sit",
  130             cond=target_height,
  131             action_id=4,
  132             action_name=f"Sit down<{target_height:.2f}>",
  133         )
  134
  135     if family_id == 5:
  136         match = re.search(r"\d+(?:\.\d+)?", action_name)
  137         distance = (
  138             max(0.10, min(0.60, float(match.group(0)))) if match else 0.25
  139         )
  140         return SkillCall(
  141             skill="step_back",

```

```text

  148         direction = (
  149             "right"
  150             if "right" in tokens or "right" in action_name.lower()
  151             else "left"
  152         )
  153         number_text = " ".join(tokens[1:]) if len(tokens) >= 2 else action_name
  154         match = re.search(r"\d+(?:\.\d+)?", number_text)
  155         distance = (
  156             max(0.10, min(0.50, float(match.group(0)))) if match else 0.25
  157         )
  158         signed_x = distance if direction == "left" else -distance
  159         return SkillCall(
  160             skill="side_walk",
  161             cond=signed_x,
  162             action_id=6,
  163             action_name=f"Side step<{direction}><{distance:.2f}>",
  164         )
  165
  166     if family_id == 7:
  167         return SkillCall(
  168             skill="step_climb_down",
  169             cond=[0.20, 0.40],

```

<a id="hc5"></a>

## HC5: src/humanclaw_bench/evaluation/metrics/episode.py

Snapshot: `local`. SHA256: `9285e410ec2fd35ce7a6af98c44c392c40f1c2e6bb3a48da89900242f5d10a39`.

```text

  140         # One environment collision query supplies all three contact
  141         # consumers. Collision sees fixed geometry, disturbance sees dynamic
  142         # object edges, and interaction sees pelvis/target mesh contacts.
  143         self.collision.record_step(step, metric_frames)
  144         self.disturbance.record_step(step, metric_frames)
  145         agent_frames = list(metric_frames.get("agent_contacts") or [])
  146         last_frame_hits = [
  147             bool(self.env.is_pelvis_target_contact(contact))
  148             for contact in (agent_frames[-1] if agent_frames else [])
  149         ]
  150         last_frame_contact = any(last_frame_hits)
  151         self._last_motion_pelvis_target_contact = last_frame_contact
  152         if str(action_skill) == "sit":
  153             self.n_sit += 1
  154             # The final paper variant evaluates the landed pose of each Sit
  155             # decision.  A transient contact earlier inside the 15-frame Sit
  156             # chunk does not count unless it remains on that action's last
  157             # physics frame (the historical ``last_frame_contacts`` field).
  158             self.geo_interact_success = (
  159                 self.geo_interact_success or last_frame_contact
  160             )
  161

```

```text

  198         # InteractSR is an active committed stop after at least one Sit, with
  199         # pelvis-to-target mesh contact on the final frame of the last motion.
  200         interact_success = bool(
  201             is_interact
  202             and self.active_stop
  203             and self.n_sit > 0
  204             and self._last_motion_pelvis_target_contact
  205         )
  206         return {

```

<a id="hc6"></a>

## HC6: src/humanclaw_bench/envs/find_nav_interact_env.py

Snapshot: `local`. SHA256: `9e544c05ad74a25de5b6555034a2366a4320a0a46b06a34ccc150bd8ac3bcf80`.

```text

  393     def is_pelvis_target_contact(self, contact: dict[str, Any]) -> bool:
  394         """Match a pelvis contact to an exact resolved goal mesh instance."""
  395
  396         if str(contact.get("body_part") or "").lower() not in {"pelvis", "base"}:
  397             return False
  398         target_ids: set[int] = set()
  399         target_handles: set[str] = set()
  400         target_templates: set[str] = set()
  401         for ref, obj in self._target_objects():
  402             target_handles.add(ref["handle"])
  403             target_templates.add(_template_hash(ref["handle"]))
  404             try:
  405                 target_ids.add(int(obj.object_id))
  406             except Exception:
  407                 pass
  408         other = contact.get("other") or {}
  409         try:
  410             if (
  411                 int(contact.get("other_object_id", other.get("object_id")))
  412                 in target_ids
  413             ):
  414                 return True
  415         except (TypeError, ValueError):
  416             pass
  417         handle = str(other.get("name") or "")
  418         return handle in target_handles or any(
  419             template and template in handle for template in target_templates
  420         )
  421

```

<a id="pi1"></a>

## PI1: packages/coding-agent/src/core/system-prompt.ts

Snapshot: `pi-1.3.0`. SHA256: `5e28c82634113d0cca7ff5da6fa94e27aaae80e461cd5664ced9dbcef6f89089`.

```text

  128 export function buildSystemPromptSections(input: BuildSystemPromptOptions): SystemPromptSections {
  129 	const options = normalizeBuildSystemPromptOptions(input);
  130 	const {
  131 		customPrompt,
  132 		selectedTools,
  133 		hiddenTools,
  134 		toolSnippets,
  135 		toolGuidelines,
  136 		promptGuidelines,
  137 		appendSystemPrompt,
  138 		sections: customSections,
  139 		cwd,
  140 		contextFiles,
  141 		skills,
  142 	} = options;
  143
  144 	for (const name of Object.keys(customSections)) {
  145 		if (!SYSTEM_PROMPT_SECTION_NAME.test(name) || name === "preamble") {
  146 			throw new Error(`Invalid system prompt section name: ${name}`);
  147 		}
  148 	}
  149
  150 	const declaredTools = selectedTools.filter((name) => !hiddenTools.includes(name));
  151 	const promptSections: Record<string, string> = {};
  152 	if (customPrompt) {
  153 		promptSections.preamble = customPrompt;
  154 	} else {
  155 		promptSections.preamble =
  156 			"You are an expert coding assistant operating inside pi, a coding agent harness. You help users by reading files, executing commands, editing code, and writing new files.";
  157 		const visibleTools = declaredTools.filter((name) => !!toolSnippets[name]);
  158 		const tools =
  159 			visibleTools.length > 0 ? visibleTools.map((name) => `- ${name}: ${toolSnippets[name]}`).join("\n") : "(none)";
  160 		promptSections.tools = `${tools}\n\nIn addition to the tools above, you may have access to other custom tools depending on the project.`;
  161 		promptSections.rules = buildRules(declaredTools, toolGuidelines, promptGuidelines);
  162 		promptSections.docs = `Pi documentation (read only when the user asks about pi itself, its SDK, extensions, themes, skills, or TUI):
  163 - Main documentation: ${getReadmePath()}
  164 - Additional docs: ${getDocsPath()}
  165 - Examples: ${getExamplesPath()} (extensions, custom tools, SDK)
  166 - When reading pi docs or examples, resolve docs/... under Additional docs and examples/... under Examples, not the current working directory
  167 - When asked about: extensions (docs/extensions.md, examples/extensions/), themes (docs/themes.md), skills (docs/skills.md), prompt templates (docs/prompt-templates.md), TUI components (docs/tui.md), keybindings (docs/keybindings.md), SDK integrations (docs/sdk.md), custom providers (docs/custom-provider.md), adding models (docs/models.md), pi packages (docs/packages.md), environment variables (docs/environment-variables.md), MCP servers (docs/mcp.md), codemode scripts and non-LLM models such as classifiers and image models (docs/codemode.md)
  168 - When working on pi topics, read the docs and examples, and follow .md cross-references before implementing
  169 - Always read pi .md files completely and follow links to related docs (e.g., tui.md for TUI API details)`;
  170 	}
  171
  172 	if (appendSystemPrompt) promptSections.addendum = appendSystemPrompt;
  173 	if (contextFiles.length > 0) promptSections.project_context = renderProjectContext(contextFiles);
  174 	// A hidden reader is still reachable through another tool, so skills stay but the hint names no tool.
  175 	const readers = ["read", "bash"] as const;

```

```text

  212 /**
  213  * Diff the sections the model currently has (replayed from the transcript, so never null)
  214  * against the desired ones. Returns a `SystemMessage.sections` patch, or undefined when
  215  * nothing changed.
  216  */
  217 export function diffSystemPromptSections(
  218 	previous: Record<string, string | null>,
  219 	current: SystemPromptSections,
  220 ): Record<string, string | null> | undefined {
  221 	const patch: Record<string, string | null> = {};
  222 	for (const [name, text] of Object.entries(current)) {
  223 		if (previous[name] !== text) patch[name] = text;
  224 	}
  225 	for (const name of Object.keys(previous)) {
  226 		if (current[name] === undefined) patch[name] = null;
  227 	}
  228 	return Object.keys(patch).length > 0 ? patch : undefined;
  229 }

```

<a id="pi2"></a>

## PI2: packages/coding-agent/src/core/sdk.ts

Snapshot: `pi-1.3.0`. SHA256: `61f398403c7510bec849583b2c46272df11ac5aa8d2e24b4ded97a108dd55b28`.

```text

   65 	 * Optional default tool suppression mode when no explicit allowlist is provided.
   66 	 *
   67 	 * - "all": start with no tools enabled
   68 	 * - "builtin": disable the default built-in tools (read, bash, edit, write)
   69 	 *   but keep extension/custom tools enabled
   70 	 */
   71 	noTools?: "all" | "builtin";
   72 	/**
   73 	 * Optional allowlist of tool names or patterns, where `*` matches any characters.
   74 	 *
   75 	 * When omitted, pi uses the resolved `defaultTools` setting for the initial
   76 	 * selection when configured. Otherwise it enables the default built-in tools
   77 	 * (read, bash, edit, write). Extension/custom tools remain enabled unless
   78 	 * `noTools` changes that default. When provided, only matching tools are
   79 	 * enabled. MCP tools stay registered for codemode and tool search unless an
   80 	 * entry starts with `mcp__`; then only matching MCP tools are kept. An empty
   81 	 * list, like `noTools: "all"`, disables MCP tools too.
   82 	 *
   83 	 * A list of only `+name` and `-name` entries is not an allowlist: it adds tools
   84 	 * to or removes them from the default selection, like the `defaultTools` setting.
   85 	 * These entries take exact names. Mixing them with plain entries throws.
   86 	 */
   87 	tools?: string[];
   88 	/**

```

```text

  372 			const currentModel = agent.state.model;
  373 			const currentMessages = agent.state.messages;
  374 			return (
  375 				currentModel.provider === requestModel.provider &&
  376 				currentModel.id === requestModel.id &&
  377 				messages.length <= currentMessages.length &&
  378 				messages.every((message, index) => currentMessages[index] === message)

```

```text

  412 		initialState: {
  413 			systemPrompt: "",
  414 			model,
  415 			thinkingLevel,
  416 			tools: [],
  417 			messages: existingSession.messages,
  418 		},
  419 		convertToLlm: convertToLlmWithBlockImages,
  420 		streamFn: async (model, context, options) => {
  421 			const requestOptions = buildRequestOptions(model, options);
  422 			// Compaction and summaries use their own routing ids; only session requests
  423 			// replace the cache entry, so warming restarts from them. Keep warming while
  424 			// the current transcript still extends the request's prefix. Agent state may
  425 			// shallow-copy the messages array or refresh the model object without changing
  426 			// the provider request, so top-level object identity is not a valid cache key.
  427 			if (options?.sessionId === sessionManager.getSessionId()) {
  428 				cacheWarmer.start({ model, context, options: requestOptions }, cacheContextIsCurrent(model));
  429 			}
  430 			return modelRuntime.streamSimple(model, context, requestOptions);
  431 		},
  432 		onPayload: transformProviderPayload,
  433 		onResponse: handleProviderResponse,
  434 		onProviderStreamEvent: handleProviderStreamEvent,
  435 		sessionId: sessionManager.getSessionId(),
  436 		transformContext: async (messages) => {
  437 			const runner = extensionRunnerRef.current;
  438 			if (!runner) return messages;
  439 			return runner.emitContext(messages);
  440 		},
  441 		steeringMode: settingsManager.getSteeringMode(),
  442 		followUpMode: settingsManager.getFollowUpMode(),
  443 		transport: settingsManager.getTransport(),
  444 		thinkingBudgets: settingsManager.getThinkingBudgets(),
  445 		maxRetryDelayMs: settingsManager.getProviderRetrySettings().maxRetryDelayMs,
  446 	});
  447
  448 	// Restore missing settings metadata for older sessions.

```

<a id="pi3"></a>

## PI3: packages/agent/src/agent.ts

Snapshot: `pi-1.3.0`. SHA256: `7024a3145a6ebc951a0f030164adb1dfb12d33d6e0dbbac15ef0efda49c87457`.

```text

  113 /** Options for constructing an {@link Agent}. */
  114 export interface AgentOptions {
  115 	initialState?: AgentInitialState;
  116 	convertToLlm?: (messages: AgentMessage[]) => Message[] | Promise<Message[]>;
  117 	transformContext?: (messages: AgentMessage[], signal?: AbortSignal) => Promise<AgentMessage[]>;
  118 	streamFn: StreamFn;
  119 	getApiKey?: (provider: string) => Promise<string | undefined> | string | undefined;
  120 	onPayload?: SimpleStreamOptions["onPayload"];
  121 	onResponse?: SimpleStreamOptions["onResponse"];
  122 	onProviderStreamEvent?: SimpleStreamOptions["onProviderStreamEvent"];
  123 	beforeToolCall?: (context: BeforeToolCallContext, signal?: AbortSignal) => Promise<BeforeToolCallResult | undefined>;
  124 	afterToolCall?: (context: AfterToolCallContext, signal?: AbortSignal) => Promise<AfterToolCallResult | undefined>;
  125 	finishTurn?: FinishTurn;
  126 	prepareRequest?: PrepareRequest;
  127 	prepareNextTurn?: (
  128 		signal?: AbortSignal,
  129 	) => Promise<AgentLoopTurnUpdate | undefined> | AgentLoopTurnUpdate | undefined;
  130 	prepareNextTurnWithContext?: (
  131 		context: PrepareNextTurnContext,
  132 		signal?: AbortSignal,
  133 	) => Promise<AgentLoopTurnUpdate | undefined> | AgentLoopTurnUpdate | undefined;
  134 	steeringMode?: QueueMode;
  135 	followUpMode?: QueueMode;
  136 	sessionId?: string;
  137 	thinkingBudgets?: ThinkingBudgets;
  138 	transport?: Transport;
  139 	maxRetryDelayMs?: number;
  140 	toolExecution?: ToolExecutionMode;
  141 }
  142
  143 class PendingMessageQueue {
  144 	private messages: AgentMessage[] = [];

```

```text

  231 		// Older compiled consumers may omit options or streamFn even though the current API requires them.
  232 		const runtimeOptions: Partial<AgentOptions> = options ?? {};
  233 		this._state = createMutableAgentState(runtimeOptions.initialState);
  234 		this.convertToLlm = runtimeOptions.convertToLlm ?? defaultConvertToLlm;
  235 		this.transformContext = runtimeOptions.transformContext;
  236 		this.streamFunction = runtimeOptions.streamFn ?? getDefaultStreamFn();
  237 		this.getApiKey = runtimeOptions.getApiKey;
  238 		this.onPayload = runtimeOptions.onPayload;
  239 		this.onResponse = runtimeOptions.onResponse;
  240 		this.onProviderStreamEvent = runtimeOptions.onProviderStreamEvent;
  241 		this.beforeToolCall = runtimeOptions.beforeToolCall;
  242 		this.afterToolCall = runtimeOptions.afterToolCall;
  243 		this.finishTurn = runtimeOptions.finishTurn;
  244 		this.prepareRequest = runtimeOptions.prepareRequest;
  245 		this.prepareNextTurn = runtimeOptions.prepareNextTurn;
  246 		this.prepareNextTurnWithContext = runtimeOptions.prepareNextTurnWithContext;
  247 		this.steeringQueue = new PendingMessageQueue(runtimeOptions.steeringMode ?? "one-at-a-time");
  248 		this.followUpQueue = new PendingMessageQueue(runtimeOptions.followUpMode ?? "one-at-a-time");
  249 		this.sessionId = runtimeOptions.sessionId;
  250 		this.thinkingBudgets = runtimeOptions.thinkingBudgets;
  251 		this.transport = runtimeOptions.transport ?? "auto";
  252 		this.maxRetryDelayMs = runtimeOptions.maxRetryDelayMs;
  253 		this.toolExecution = runtimeOptions.toolExecution ?? "parallel";
  254 	}

```

<a id="pi4"></a>

## PI4: packages/agent/src/agent-loop.ts

Snapshot: `pi-1.3.0`. SHA256: `28a2b03e34a7e32f004aa851e54d3b5be9dad71c392205614cbc9abdf3a9020a`.

```text

  260
  261 			const toolResults: ToolResultMessage[] = [];
  262 			hasMoreToolCalls = false;
  263 			if (toolCalls.length > 0) {
  264 				// A "length" stop means the output was cut off by the token limit, so
  265 				// every tool call in the message may carry truncated arguments. Fail
  266 				// them all instead of executing potentially borked calls.
  267 				const executedToolBatch =
  268 					message.stopReason === "length"
  269 						? await failToolCallsFromTruncatedMessage(toolCalls, emit)
  270 						: await executeToolCalls(currentContext, message, config, signal, emit);
  271 				toolResults.push(...executedToolBatch.messages);
  272 				hasMoreToolCalls = !executedToolBatch.terminate;
  273
  274 				for (const result of toolResults) {
  275 					currentContext.messages.push(result);
  276 					newMessages.push(result);
  277 				}
  278 			}
  279
  280 			lastCompletedTurn = {
  281 				message,
  282 				toolResults,
  283 				context: currentContext,
  284 				newMessages,
  285 			};
  286 			const decision = await config.finishTurn?.(lastCompletedTurn, signal);
  287 			await emit({ type: "turn_end", message, toolResults });
  288
  289 			if (decision?.action === "end") {
  290 				await emit({ type: "agent_end", messages: newMessages });
  291 				return;
  292 			}
  293
  294 			explicitContinuation = decision?.action === "continue";
  295 			pendingMessages = (await config.getSteeringMessages?.()) || [];
  296 			if (hasMoreToolCalls || pendingMessages.length > 0) {
  297 				explicitContinuation = false;
  298 			}
  299 		}
  300
  301 		// Agent would stop here. Check for follow-up messages.

```

```text

  381 async function streamAssistantResponse(
  382 	context: AgentContext,
  383 	config: AgentLoopConfig,
  384 	signal: AbortSignal | undefined,
  385 	emit: AgentEventSink,
  386 	streamFunction: StreamFn,
  387 ): Promise<AssistantMessage> {
  388 	// Apply context transform if configured (AgentMessage[] → AgentMessage[])
  389 	let messages = context.messages;
  390 	if (config.transformContext) {
  391 		messages = await config.transformContext(messages, signal);
  392 	}
  393
  394 	// Convert to LLM-compatible messages (AgentMessage[] → Message[])
  395 	const llmMessages = await config.convertToLlm(messages);
  396
  397 	const llmContext = normalizeContext({ messages: llmMessages });
  398
  399 	// Resolve API key (important for expiring tokens)
  400 	const resolvedApiKey =
  401 		(config.getApiKey ? await config.getApiKey(config.model.provider) : undefined) || config.apiKey;
  402
  403 	const response = await streamFunction(config.model, llmContext, {
  404 		...config,
  405 		apiKey: resolvedApiKey,

```

```text

  505 /**
  506  * Execute tool calls from an assistant message.
  507  */
  508 async function executeToolCalls(
  509 	currentContext: AgentContext,
  510 	assistantMessage: AssistantMessage,
  511 	config: AgentLoopConfig,
  512 	signal: AbortSignal | undefined,
  513 	emit: AgentEventSink,
  514 ): Promise<ExecutedToolCallBatch> {
  515 	const toolCalls = assistantMessage.content.filter((c) => c.type === "toolCall");
  516 	const hasSequentialToolCall = toolCalls.some(
  517 		(tc) => currentContext.tools?.find((t) => t.name === tc.name)?.executionMode === "sequential",
  518 	);
  519 	if (config.toolExecution === "sequential" || hasSequentialToolCall) {
  520 		return executeToolCallsSequential(currentContext, assistantMessage, toolCalls, config, signal, emit);
  521 	}
  522 	return executeToolCallsParallel(currentContext, assistantMessage, toolCalls, config, signal, emit);
  523 }
  524
  525 type ExecutedToolCallBatch = {
  526 	messages: ToolResultMessage[];
  527 	terminate: boolean;
  528 };
  529
  530 async function executeToolCallsSequential(
  531 	currentContext: AgentContext,
  532 	assistantMessage: AssistantMessage,
  533 	toolCalls: AgentToolCall[],
  534 	config: AgentLoopConfig,

```

```text

  708 async function prepareToolCall(
  709 	currentContext: AgentContext,
  710 	assistantMessage: AssistantMessage,
  711 	toolCall: AgentToolCall,
  712 	config: ToolCallHooks,
  713 	signal: AbortSignal | undefined,
  714 	tools: readonly AgentTool<any>[] = currentContext.tools ?? [],
  715 ): Promise<PreparedToolCall | ImmediateToolCallOutcome> {
  716 	const tool = tools.find((t) => t.name === toolCall.name);
  717 	if (!tool) {
  718 		return {
  719 			kind: "immediate",
  720 			result: createErrorToolResult(`Tool ${toolCall.name} not found`),
  721 			isError: true,
  722 		};
  723 	}
  724
  725 	try {
  726 		const preparedToolCall = prepareToolCallArguments(tool, toolCall);
  727 		const validatedArgs = validateToolArguments(tool, preparedToolCall);
  728 		if (config.beforeToolCall) {
  729 			const beforeResult = await config.beforeToolCall(
  730 				{
  731 					assistantMessage,
  732 					toolCall,
  733 					args: validatedArgs,
  734 					context: currentContext,
  735 				},
  736 				signal,
  737 			);
  738 			if (signal?.aborted) {
  739 				return {
  740 					kind: "immediate",
  741 					result: createErrorToolResult("Operation aborted"),
  742 					isError: true,
  743 				};
  744 			}
  745 			if (beforeResult?.block) {
  746 				const result = createErrorToolResult(beforeResult.reason || "Tool execution was blocked");
  747 				if (beforeResult.terminate === true) {
  748 					result.terminate = true;
  749 				}
  750 				return {
  751 					kind: "immediate",
  752 					result,
  753 					isError: true,
  754 				};
  755 			}
  756 		}
  757 		if (signal?.aborted) {
  758 			return {
  759 				kind: "immediate",
  760 				result: createErrorToolResult("Operation aborted"),
  761 				isError: true,
  762 			};
  763 		}

```

```text

  859 async function finalizeExecutedToolCall(
  860 	currentContext: AgentContext,
  861 	assistantMessage: AssistantMessage,
  862 	prepared: PreparedToolCall,
  863 	executed: ExecutedToolCallOutcome,
  864 	config: ToolCallHooks,
  865 	signal: AbortSignal | undefined,
  866 ): Promise<FinalizedToolCallOutcome> {
  867 	let result = executed.result;
  868 	let isError = executed.isError;
  869
  870 	if (config.afterToolCall) {
  871 		try {
  872 			const afterResult = await config.afterToolCall(
  873 				{
  874 					assistantMessage,
  875 					toolCall: prepared.toolCall,
  876 					args: prepared.args,
  877 					result,
  878 					isError,
  879 					context: currentContext,
  880 				},
  881 				signal,
  882 			);
  883 			if (afterResult) {
  884 				// Structured content not replaced along with the content may no longer match it.
  885 				const structuredContent =
  886 					afterResult.structuredContent ?? (afterResult.content ? undefined : result.structuredContent);
  887 				result = {
  888 					...result,
  889 					content: afterResult.content ?? result.content,
  890 					details: afterResult.details ?? result.details,
  891 					usage: afterResult.usage ?? result.usage,
  892 					terminate: afterResult.terminate ?? result.terminate,
  893 				};
  894 				if (structuredContent === undefined) delete result.structuredContent;
  895 				else result.structuredContent = structuredContent;
  896 				isError = afterResult.isError ?? isError;
  897 			}
  898 		} catch (error) {
  899 			result = createErrorToolResult(error instanceof Error ? error.message : String(error));
  900 			isError = true;
  901 		}
  902 	}
  903

```

<a id="pi5"></a>

## PI5: packages/coding-agent/src/core/agent-session.ts

Snapshot: `pi-1.3.0`. SHA256: `e0fa206e8c49a98c024708068df39c0e4944f4251633425fc083b2fbb5ec0ac6`.

```text

  380 	readonly agent: Agent;

```

```text

  649 	 * new runner without reinstalling hooks. Extension-specific tool wrappers are still used to adapt
  650 	 * registered tool execution to the extension context. Tool call and tool result interception now
  651 	 * happens here instead of in wrappers.
  652 	 */
  653 	private _installAgentToolHooks(): void {
  654 		this.agent.beforeToolCall = (context) => this._beforeToolCall(context);
  655 		this.agent.afterToolCall = (context) => this._afterToolCall(context);
  656 	}
  657
  658 	/** `tool_call` handlers. `parentToolCallId` is set for calls another tool made. */
  659 	private async _beforeToolCall(
  660 		{ toolCall, args }: BeforeToolCallContext,
  661 		parentToolCallId?: string,
  662 	): Promise<BeforeToolCallResult | undefined> {
  663 		const runner = this._extensionRunner;
  664 		if (!runner.hasHandlers("tool_call")) {
  665 			return undefined;
  666 		}
  667
  668 		try {
  669 			return await runner.emitToolCall({
  670 				type: "tool_call",
  671 				toolName: toolCall.name,
  672 				toolCallId: toolCall.id,
  673 				...(parentToolCallId ? { parentToolCallId } : {}),
  674 				input: args as Record<string, unknown>,
  675 			});
  676 		} catch (err) {
  677 			if (err instanceof Error) {
  678 				throw err;
  679 			}
  680 			throw new Error(`Extension failed, blocking execution: ${String(err)}`);
  681 		}
  682 	}
  683
  684 	/** `tool_result` handlers and image normalization. `parentToolCallId` is set for calls another tool made. */
  685 	private async _afterToolCall(
  686 		{ toolCall, args, result, isError }: AfterToolCallContext,
  687 		parentToolCallId?: string,
  688 	): Promise<AfterToolCallResult | undefined> {
  689 		const runner = this._extensionRunner;
  690 		const hookResult = runner.hasHandlers("tool_result")
  691 			? await runner.emitToolResult({
  692 					type: "tool_result",
  693 					toolName: toolCall.name,
  694 					toolCallId: toolCall.id,
  695 					...(parentToolCallId ? { parentToolCallId } : {}),
  696 					input: args as Record<string, unknown>,
  697 					content: result.content,
  698 					details: result.details,
  699 					...(result.structuredContent === undefined ? {} : { structuredContent: result.structuredContent }),
  700 					isError,
  701 					usage: result.usage,
  702 				})
  703 			: undefined;
  704
  705 		const content = hookResult?.content ?? result.content ?? [];
  706 		// Runs after the extension hook so images injected or replaced by extensions are normalized too.
  707 		const resizeOptions = this._limitsModel()?.inputLimits?.images?.resize;
  708 		const normalizedContent = await normalizeToolResultImages(content, {
  709 			autoResizeImages: this.settingsManager.getImageAutoResize(),
  710 			...(resizeOptions ? { resizeOptions } : {}),
  711 		});
  712
  713 		if (!hookResult && normalizedContent === content) {
  714 			return undefined;
  715 		}
  716
  717 		// The hook result already dropped structured content that replaced content no longer matches.
  718 		return {
  719 			content: normalizedContent,
  720 			details: hookResult?.details,
  721 			structuredContent: hookResult ? hookResult.structuredContent : result.structuredContent,
  722 			isError: hookResult?.isError ?? isError,
  723 			usage: hookResult?.usage,
  724 		};

```

```text

  887 	private _installAgentBoundaryHooks(): void {
  888 		const previousFinishTurn = this.agent.finishTurn;
  889 		this.agent.finishTurn = async (turn, signal) => {
  890 			this._boundaryDispatchedMessages.add(turn.message);
  891 			const extensionContinue = await this._dispatchTurnEndBoundary(turn.message, turn.toolResults);
  892 			const previousDecision = await previousFinishTurn?.(turn, signal);
  893 			if (previousDecision?.action === "end") return previousDecision;
  894 			if (extensionContinue || previousDecision?.action === "continue") return { action: "continue" };
  895 			return undefined;
  896 		};
  897 	}
  898
  899 	private _installAgentNextTurnRefresh(): void {
  900 		const previousPrepareNextTurnWithContext =
  901 			this.agent.prepareNextTurnWithContext ??
  902 			(this.agent.prepareNextTurn
  903 				? async (_turn: PrepareNextTurnContext, signal?: AbortSignal) => await this.agent.prepareNextTurn?.(signal)
  904 				: undefined);
  905 		this.agent.prepareNextTurnWithContext = async (turn, signal) => {
  906 			const context = await this._compactBeforeNextAssistantResponse(turn.context);
  907 			const previousSnapshot = await previousPrepareNextTurnWithContext?.({ ...turn, context }, signal);
  908 			const nextContext = previousSnapshot?.context ?? context;
  909 			const runOptions = this._runSystemPromptOptions ?? this._baseSystemPromptOptions;
  910 			const options = normalizeBuildSystemPromptOptions({
  911 				...runOptions,
  912 				selectedTools: this.getActiveToolNames(),
  913 				toolSnippets: { ...this._baseSystemPromptOptions.toolSnippets, ...runOptions.toolSnippets },
  914 				toolGuidelines: { ...this._baseSystemPromptOptions.toolGuidelines, ...runOptions.toolGuidelines },
  915 			});

```

```text

 3274 	}
 3275
 3276 	/**
 3277 	 * Toggle auto-compaction setting.
 3278 	 */
 3279 	setAutoCompactionEnabled(enabled: boolean): void {
 3280 		this.settingsManager.setCompactionEnabled(enabled);
 3281 	}
 3282
 3283 	/** Whether auto-compaction is enabled */
 3284 	get autoCompactionEnabled(): boolean {
 3285 		return this.settingsManager.getCompactionEnabled();
 3286 	}
 3287

```

<a id="pi6"></a>

## PI6: packages/coding-agent/src/core/extensions/types.ts

Snapshot: `pi-1.3.0`. SHA256: `cb54c7a4fedb3473bb995694bbc1f2988c144fb0b802bfd1b656816bc25d0f25`.

```text

 1444 	messages?: AgentMessage[];
 1445 }
 1446
 1447 export type TurnEndEventResult = BoundaryResult;
 1448 export type AgentBeforeSettleEventResult = BoundaryResult;
 1449
 1450 export type BeforeProviderRequestEventResult = unknown;
 1451
 1452 export type { CacheWarmingDecisionEvent, CacheWarmingDecisionEventResult } from "../cache-warmer.ts";
 1453
 1454 export interface ToolCallEventResult {
 1455 	/** Block tool execution. To modify arguments, mutate `event.input` in place instead. */
 1456 	block?: boolean;
 1457 	reason?: string;
 1458 	/**
 1459 	 * Hint that the agent should stop after the current tool batch when this call is blocked.
 1460 	 * Early termination only happens when every finalized tool result in the batch sets this to true.
 1461 	 */
 1462 	terminate?: boolean;
 1463 }

```

```text

 1478 /**
 1479  * Changes a `tool_result` handler makes. Omitted fields stay as they are, except that replacing
 1480  * `content` without returning `structuredContent` drops the structured content, because it may no
 1481  * longer match. Return it along with `content` to keep it.
 1482  */
 1483 export interface ToolResultEventResult {
 1484 	content?: (TextContent | ImageContent)[];
 1485 	details?: unknown;
 1486 	structuredContent?: JsonValue;
 1487 	isError?: boolean;
 1488 	usage?: Usage;
 1489 }
 1490
 1491 export interface MessageEndEventResult {
 1492 	/** Replace the finalized message. The replacement must keep the original message role. */
 1493 	message?: AgentMessage;
 1494 }
 1495
 1496 export interface BeforeAgentStartEventResult {
 1497 	message?: Pick<CustomMessage, "customType" | "content" | "display" | "details">;
 1498 	/** Replace the complete system prompt for this turn. Later handlers observe this exact override. */
 1499 	systemPrompt?: string;
 1500 }
 1501
 1502 export interface SessionBeforeSwitchResult {
 1503 	cancel?: boolean;
 1504 }
 1505

```

```text

 1772 	getSettings(): Settings;
 1773
 1774 	/**
 1775 	 * Set the active tools by name. Unknown and `hidden` tools are ignored. Tools with `codemode` or
 1776 	 * `deferred` exposure stay callable from codemode scripts whether active or not.
 1777 	 */
 1778 	setActiveTools(toolNames: string[]): void;
 1779
 1780 	/** Get available slash commands in the current session. */
 1781 	getCommands(): SlashCommandInfo[];
 1782
 1783 	// =========================================================================
 1784 	// Model and Thinking Level
 1785 	// =========================================================================
 1786
 1787 	/**
 1788 	 * Set the model for the current session without changing the configured default for new sessions.
 1789 	 * Returns false if authentication is not configured for the model's provider.
 1790 	 */
 1791 	setModel(model: Model<any>): Promise<boolean>;
 1792
 1793 	/** Get current thinking level. */
 1794 	getThinkingLevel(): ThinkingLevel;
 1795
 1796 	/**
 1797 	 * Set the thinking level (clamped to model capabilities) for the current session without changing the configured default
 1798 	 * for new sessions.
 1799 	 */
 1800 	setThinkingLevel(level: ThinkingLevel): void;
 1801
 1802 	// =========================================================================
 1803 	// Provider Registration

```

<a id="pi7"></a>

## PI7: packages/coding-agent/src/extensions/mcp/tools.ts

Snapshot: `pi-1.3.0`. SHA256: `cd3245946deb3cb3df2e7b521a07837525f886d281c5e4600527eb2aed95e2ac`.

```text

  291  */
  292 function toParameters(schema: Record<string, unknown>): TSchema {
  293 	return {
  294 		...schema,
  295 		type: schema.type ?? "object",
  296 		...(schema.properties === undefined ? { properties: {} } : {}),
  297 	} as unknown as TSchema;
  298 }
  299

```

```text

  311
  312 export function createMcpToolDefinition(options: {
  313 	server: string;
  314 	tool: McpTool;
  315 	name: string;
  316 	exposure: McpExposure;
  317 	namespace: ToolNamespace;
  318 	timeoutMs: number;
  319 	getClient: () => Promise<McpToolCaller>;
  320 	/** Whether `read_mcp_resource` can read the server's resources. */
  321 	readableResources?: () => boolean;
  322 }): ToolDefinition<TSchema, McpToolDetails> {
  323 	const { server, tool } = options;
  324 	const title = tool.title ?? tool.annotations?.title;
  325 	const annotations = toToolAnnotations(tool);
  326 	const label = `${server}/${tool.name}`;
  327 	return {
  328 		name: options.name,
  329 		label,
  330 		description: tool.description?.trim() || title || `MCP tool ${tool.name} from server ${server}`,
  331 		parameters: toParameters(tool.inputSchema),
  332 		outputSchema: createMcpResultSchema(tool.outputSchema),
  333 		exposure: toToolExposure(options.exposure),
  334 		namespace: options.namespace,
  335 		...(annotations ? { annotations } : {}),
  336 		...createMcpToolRenderers(label),
  337 		async execute(_toolCallId, params, signal, onUpdate) {
  338 			const client = await options.getClient();
  339 			const result = await client.callTool(tool.name, (params ?? {}) as Record<string, unknown>, {
  340 				signal,
  341 				timeoutMs: options.timeoutMs,
  342 				onProgress: (progress) => {
  343 					const total = progress.total === undefined ? "" : `/${progress.total}`;
  344 					const text = progress.message ?? `Progress ${progress.progress}${total}`;
  345 					onUpdate?.({ content: [{ type: "text", text }], details: { server, tool: tool.name } });
  346 				},
  347 			});
  348 			return convertMcpResult(server, tool.name, result, { readableResources: options.readableResources?.() });
  349 		},
  350 	};
  351 }
  352
  353 /** Renderers of calls to an MCP tool, labeled `server/tool`, also used before the tool is registered. */
  354 export function createMcpToolRenderers(label: string): ToolRenderers {
  355 	return {

```

<a id="pi8"></a>

## PI8: packages/ai/src/api/openai-responses-shared.ts

Snapshot: `pi-1.3.0`. SHA256: `f940a1539a3ca03fbee79b2c848999e0b51c74f7cceb45484d3d52bc2303de3c`.

```text

   72 			}
   73 		} catch {
   74 			// Fall through to legacy plain-string handling.
   75 		}
   76 	}
   77 	return { id: signature };
   78 }
   79
   80 type ToolResultOutputContent = Array<ResponseInputText | ResponseInputImage>;
   81
   82 function convertToolResultOutput<TApi extends Api>(
   83 	model: Model<TApi>,
   84 	content: readonly (TextContent | ImageContent)[],
   85 ): string | ToolResultOutputContent {
   86 	const textResult = content
   87 		.filter((c): c is TextContent => c.type === "text")
   88 		.map((c) => c.text)

```

```text

  156 export function convertResponsesMessages<TApi extends Api>(
  157 	model: Model<TApi>,
  158 	context: TranscriptContext,
  159 	allowedToolCallProviders: ReadonlySet<string>,
  160 	options?: ConvertResponsesMessagesOptions,
  161 ): ResponseInput {
  162 	const normalizedContext = resolveTranscript(context, options?.supportsMidConvoSystemMessages);
  163 	const messages: ResponseInput = [];
  164
  165 	const normalizeIdPart = (part: string): string => {
  166 		const sanitized = part.replace(/[^a-zA-Z0-9_-]/g, "_");
  167 		const normalized = sanitized.length > 64 ? sanitized.slice(0, 64) : sanitized;
  168 		return normalized.replace(/_+$/, "");
  169 	};
  170
  171 	const buildForeignResponsesItemId = (itemId: string): string => {
  172 		const normalized = `fc_${shortHash(itemId)}`;
  173 		return normalized.length > 64 ? normalized.slice(0, 64) : normalized;
  174 	};
  175
  176 	const normalizeToolCallId = (id: string, _targetModel: Model<TApi>, source: AssistantMessage): string => {
  177 		if (!allowedToolCallProviders.has(model.provider)) return normalizeIdPart(id);

```

```text

  385 export function convertResponsesTools(tools: readonly Tool[], options?: ConvertResponsesToolsOptions): OpenAITool[] {
  386 	const defaultStrict = options?.strict === undefined ? false : options.strict;
  387 	const supportsStrictMode = options?.supportsStrictMode ?? true;
  388 	const supportsOpenAIGrammarTools = options?.supportsOpenAIGrammarTools ?? false;
  389
  390 	return tools.map((tool) => {
  391 		const grammar = resolveGrammarConstrainedSampling(tool, supportsOpenAIGrammarTools);
  392 		if (grammar) {
  393 			return {
  394 				type: "custom",
  395 				name: tool.name,
  396 				description: tool.description,
  397 				format: {
  398 					type: "grammar",
  399 					syntax: grammar.format,
  400 					definition: grammar.definition,
  401 				},
  402 				...(options?.toolSearchResult ? { defer_loading: true } : {}),
  403 			} satisfies OpenAITool;
  404 		}
  405
  406 		const constrainedStrict = resolveJsonSchemaStrictSampling(tool, supportsStrictMode);
  407 		const strict = constrainedStrict ?? defaultStrict;
  408 		const functionTool: Omit<Extract<OpenAITool, { type: "function" }>, "strict"> & {
  409 			strict?: Extract<OpenAITool, { type: "function" }>["strict"];
  410 		} = {
  411 			type: "function",
  412 			name: tool.name,
  413 			description: tool.description,
  414 			parameters: getJsonSchemaToolParameters(tool, strict === true) as Record<string, unknown>,
  415 			...(options?.toolSearchResult ? { defer_loading: true } : {}),
  416 		};
  417 		if (supportsStrictMode) {
  418 			functionTool.strict = strict;
  419 		}
  420 		return functionTool as OpenAITool;
  421 	});
  422 }
  423
  424 // =============================================================================
  425 // Stream processing

```

<a id="pi9"></a>

## PI9: packages/ai/src/utils/validation.ts

Snapshot: `pi-1.3.0`. SHA256: `e4b8029c184bd6df830e0ee2cb7034a39d49b5ecb8c068c26af9564c20246594`.

```text

  317 export function validateToolArguments(tool: Tool, toolCall: ToolCall): any {
  318 	if (toolCall.argumentsError) {
  319 		throw new Error(`Invalid arguments for tool "${toolCall.name}": ${toolCall.argumentsError}`);
  320 	}
  321 	const args = structuredClone(toolCall.arguments);
  322 	normalizeOptionalNulls(args, tool.parameters as JsonSchemaObject);
  323 	Value.Convert(tool.parameters, args);
  324
  325 	const validator = getValidator(tool.parameters);
  326 	if (!Object.getOwnPropertySymbols(tool.parameters).includes(TYPEBOX_KIND)) {
  327 		const coerced = coerceWithJsonSchema(args, tool.parameters as JsonSchemaObject);
  328 		if (coerced !== args) {
  329 			if (typeof args === "object" && args !== null && typeof coerced === "object" && coerced !== null) {
  330 				for (const key of Object.keys(args)) {
  331 					delete args[key];
  332 				}
  333 				Object.assign(args, coerced);
  334 			} else {
  335 				return validator.Check(coerced) ? coerced : args;
  336 			}
  337 		}
  338 	}
  339
  340 	if (validator.Check(args)) {
  341 		return args;
  342 	}
  343
  344 	const errors =
  345 		validator
  346 			.Errors(args)
  347 			.map((error) => `  - ${formatValidationPath(error)}: ${error.message}`)
  348 			.join("\n") || "Unknown validation error";
  349
  350 	const errorMessage = `Validation failed for tool "${toolCall.name}":\n${errors}\n\nReceived arguments:\n${JSON.stringify(toolCall.arguments, null, 2)}`;
  351
  352 	throw new Error(errorMessage);
  353 }

```

<a id="c1"></a>

## C1: codex-rs/models-manager/src/model_info.rs

Snapshot: `codex-rust-v0.145.0`. SHA256: `da02554f893b208cbf74684ba2cac5144c0921b2347b0b21b3688bd4bafe3eeb`.

```text

   49         };
   50     }
   51
   52     if let Some(base_instructions) = &config.base_instructions {
   53         model.base_instructions = base_instructions.clone();
   54         clear_instruction_messages(&mut model);
   55     } else {

```

```text

  124 /// Build a minimal fallback model descriptor for missing/unknown slugs.
  125 pub fn model_info_from_slug(slug: &str) -> ModelInfo {
  126     warn!("Unknown model {slug} is used. This will use fallback model metadata.");
  127     ModelInfo {
  128         slug: slug.to_string(),
  129         display_name: slug.to_string(),
  130         description: None,
  131         default_reasoning_level: None,
  132         supported_reasoning_levels: Vec::new(),
  133         shell_type: ConfigShellToolType::Default,
  134         visibility: ModelVisibility::None,
  135         supported_in_api: true,
  136         priority: 99,
  137         additional_speed_tiers: Vec::new(),
  138         service_tiers: Vec::new(),
  139         default_service_tier: None,
  140         availability_nux: None,
  141         upgrade: None,
  142         base_instructions: BASE_INSTRUCTIONS.to_string(),
  143         model_messages: local_personality_messages_for_slug(slug),
  144         include_skills_usage_instructions: false,
  145         supports_reasoning_summary_parameter: true,
  146         default_reasoning_summary: ReasoningSummary::Auto,
  147         support_verbosity: false,
  148         default_verbosity: None,
  149         apply_patch_tool_type: None,
  150         web_search_tool_type: WebSearchToolType::Text,
  151         truncation_policy: TruncationPolicyConfig::bytes(/*limit*/ 10_000),
  152         supports_parallel_tool_calls: false,
  153         supports_image_detail_original: false,
  154         context_window: Some(272_000),
  155         max_context_window: Some(272_000),
  156         auto_compact_token_limit: None,
  157         comp_hash: None,

```

<a id="c2"></a>

## C2: codex-rs/tools/src/json_schema.rs

Snapshot: `codex-rust-v0.145.0`. SHA256: `ccfc96787883f2c1c3d51a61c36db34ec2d371fc1e029bef4c42683d5069748d`.

```text

   29 }
   30
   31 /// JSON Schema `type` supports either a single type name or a union of names.
   32 #[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
   33 #[serde(untagged)]
   34 pub enum JsonSchemaType {
   35     Single(JsonSchemaPrimitiveType),
   36     Multiple(Vec<JsonSchemaPrimitiveType>),
   37 }
   38
   39 /// Generic JSON-Schema subset needed for our tool definitions.
   40 #[derive(Debug, Clone, Default, Serialize, Deserialize, PartialEq)]
   41 pub struct JsonSchema {
   42     #[serde(rename = "$ref", skip_serializing_if = "Option::is_none")]
   43     pub schema_ref: Option<String>,
   44     #[serde(rename = "type", skip_serializing_if = "Option::is_none")]
   45     pub schema_type: Option<JsonSchemaType>,
   46     #[serde(skip_serializing_if = "Option::is_none")]
   47     pub description: Option<String>,
   48     /// Responses-only marker for reviewed encrypted tool parameters.
   49     #[serde(skip_serializing_if = "Option::is_none")]
   50     pub encrypted: Option<bool>,
   51     #[serde(rename = "enum", skip_serializing_if = "Option::is_none")]
   52     pub enum_values: Option<Vec<JsonValue>>,
   53     #[serde(skip_serializing_if = "Option::is_none")]
   54     pub items: Option<Box<JsonSchema>>,
   55     #[serde(skip_serializing_if = "Option::is_none")]
   56     pub properties: Option<BTreeMap<String, JsonSchema>>,
   57     #[serde(skip_serializing_if = "Option::is_none")]
   58     pub required: Option<Vec<String>>,
   59     #[serde(
   60         rename = "additionalProperties",
   61         skip_serializing_if = "Option::is_none"
   62     )]
   63     pub additional_properties: Option<AdditionalProperties>,
   64     #[serde(rename = "anyOf", skip_serializing_if = "Option::is_none")]
   65     pub any_of: Option<Vec<JsonSchema>>,
   66     #[serde(rename = "oneOf", skip_serializing_if = "Option::is_none")]
   67     pub one_of: Option<Vec<JsonSchema>>,
   68     #[serde(rename = "allOf", skip_serializing_if = "Option::is_none")]
   69     pub all_of: Option<Vec<JsonSchema>>,
   70     #[serde(rename = "$defs", skip_serializing_if = "Option::is_none")]
   71     pub defs: Option<BTreeMap<String, JsonSchema>>,
   72     #[serde(skip_serializing_if = "Option::is_none")]
   73     pub definitions: Option<BTreeMap<String, JsonSchema>>,
   74 }
   75
   76 impl JsonSchema {
   77     /// Construct a scalar/object/array schema with a single JSON Schema type.
   78     fn typed(schema_type: JsonSchemaPrimitiveType, description: Option<String>) -> Self {
   79         Self {
   80             schema_type: Some(JsonSchemaType::Single(schema_type)),
   81             description,
   82             ..Default::default()
   83         }

```

<a id="c3"></a>

## C3: codex-rs/tools/src/responses_api.rs

Snapshot: `codex-rust-v0.145.0`. SHA256: `e746442baf7f78b035b44001edcb7fccf0947004ad991d7d0860ff5cb76a2182`.

```text

  126
  127 pub fn tool_definition_to_responses_api_tool(tool_definition: ToolDefinition) -> ResponsesApiTool {
  128     ResponsesApiTool {
  129         name: tool_definition.name,
  130         description: tool_definition.description,
  131         strict: false,
  132         defer_loading: tool_definition.defer_loading.then_some(true),
  133         parameters: tool_definition.input_schema,
  134         output_schema: tool_definition.output_schema,
  135     }
  136 }
  137
  138 #[cfg(test)]
  139 #[path = "responses_api_tests.rs"]

```

<a id="c4"></a>

## C4: codex-rs/core/src/tools/context.rs

Snapshot: `codex-rust-v0.145.0`. SHA256: `84ae66534c3d1ac747f197c699d80bf98057df8ae4cedf72a9f3b33009f9eb61`.

```text

  105         })
  106     }
  107
  108     fn post_tool_use_input(&self, _payload: &ToolPayload) -> Option<JsonValue> {
  109         Some(self.tool_input.clone())
  110     }
  111
  112     fn post_tool_use_response(&self, _call_id: &str, _payload: &ToolPayload) -> Option<JsonValue> {
  113         serde_json::to_value(&self.result).ok()
  114     }
  115 }
  116
  117 impl McpToolOutput {
  118     fn response_payload(&self) -> FunctionCallOutputPayload {
  119         let mut payload = self.result.as_function_call_output_payload();
  120         if let Some(items) = payload.content_items_mut() {
  121             sanitize_original_image_detail(self.original_image_detail_supported, items);
  122         }
  123
  124         let wall_time_seconds = self.wall_time.as_secs_f64();
  125         let header = format!("Wall time: {wall_time_seconds:.4} seconds\nOutput:");
  126
  127         match &mut payload.body {
  128             FunctionCallOutputBody::Text(text) => {
  129                 if text.is_empty() {
  130                     *text = header;
  131                 } else {
  132                     *text = format!("{header}\n{text}");
  133                 }
  134             }
  135             FunctionCallOutputBody::ContentItems(items) => {
  136                 items.insert(0, FunctionCallOutputContentItem::InputText { text: header });
  137             }
  138         }
  139
  140         // This is the context-injection form, so keep it aligned with the
  141         // function-call output truncation that conversation history already
  142         // applies. Code-mode consumers still get the raw `CallToolResult`.
  143         //
  144         // The text is serialized again inside the Responses payload, so allow
  145         // a small buffer for JSON escaping and wrapper overhead.

```

<a id="c5"></a>

## C5: codex-rs/core/src/mcp_tool_call.rs

Snapshot: `codex-rust-v0.145.0`. SHA256: `3df6fee0dd8bb0f99b8476b570e8f7ed94e1b99563db878341f8c7779f60a1b1`.

```text

  118     hook_tool_name: HookToolName,
  119     arguments: String,
  120 ) -> HandledMcpToolCall {
  121     let turn_context = &step_context.turn;
  122     let manager = step_context.mcp.manager();
  123     // Parse the `arguments` as JSON. An empty string is OK, but invalid JSON
  124     // is not.
  125     let arguments_value = if arguments.trim().is_empty() {
  126         None
  127     } else {
  128         match serde_json::from_str::<serde_json::Value>(&arguments) {
  129             Ok(value) => Some(value),
  130             Err(e) => {
  131                 error!("failed to parse tool call arguments: {e}");
  132                 return HandledMcpToolCall {
  133                     result: CallToolResult::from_error_text(format!("err: {e}")),
  134                     tool_input: JsonValue::Object(serde_json::Map::new()),
  135                 };
  136             }
  137         }
  138     };
  139
  140     let invocation = McpInvocation {
  141         server: server.clone(),
  142         tool: tool_name.clone(),
  143         arguments: arguments_value.clone(),
  144     };
  145
  146     let metadata = lookup_mcp_tool_metadata(
  147         sess.as_ref(),
  148         turn_context.as_ref(),
  149         manager,
  150         &server,
  151         &tool_name,
  152     )
  153     .await;
  154     let item_metadata = McpToolCallItemMetadata::from_tool_metadata(&server, metadata.as_ref());

```
