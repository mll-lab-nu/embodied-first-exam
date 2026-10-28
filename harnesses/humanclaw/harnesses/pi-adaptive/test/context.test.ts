import test from "node:test";
import assert from "node:assert/strict";
import { ContextBuilder, cost, type Profile } from "../src/context.ts";
import type { AgentMessage } from "@earendil-works/pi-agent-core";
const profile: Profile = { version: "pi-adaptive-v1", pi_version: "1.3.0", base_effort: "medium", high_effort: "high",
  recent_exchanges: 2, trim_at_exchanges: 4, model_capabilities: { model: "test", max_images: 3, max_input_tokens: 30000, image_token_reserve: 1000 } };
function transcript(images = false): AgentMessage[] {
  const messages: any[] = [{role: "system", content: [{type: "text", text: "public tool schemas"}]}, {role: "user", content: "task", timestamp: 0}];
  for (let i = 0; i < 8; i++) {
    messages.push({role: "assistant", content: [{type: "thinking", thinking: "signed", thinkingSignature: "retain-me"}, {type: "toolCall", id: `c${i}`, name: "inspect", arguments: {}}], stopReason: "toolUse", timestamp: i});
    messages.push({role: "toolResult", toolCallId: `c${i}`, toolName: "inspect", content: [{type: "text", text: JSON.stringify({state: {current_observation: `o${i}`, feedback: "unknown"}, value: {observations:[{id:`o${i}`}]}})}, ...(images ? [{type: "image", mimeType: "image/png", data: "test"}] : [])], isError: false, timestamp: i});
  }
  return messages;
}
test("non-image environment and signed complete exchanges survive projection", () => {
  const input = transcript(), before = JSON.stringify(input);
  const output = new ContextBuilder(profile, () => {}).project(input);
  assert.equal(JSON.stringify(input), before);
  assert.ok(output.length < input.length);
  assert.match(JSON.stringify(output), /retain-me/);
  assert.match(JSON.stringify(output), /o7/);
  assert.equal(cost(output, 1000).images, 0);
});
test("current RGB and tool schema costs survive trimming", () => {
  const output = new ContextBuilder(profile, () => {}).project(transcript(true));
  assert.ok(cost(output, 1000).images <= 3);
  assert.match(JSON.stringify(output), /public tool schemas/);
  assert.match(JSON.stringify(output), /c7/);
});
test("mandatory context overflows explicitly", () => {
  const tiny = {...profile, model_capabilities: {...profile.model_capabilities, max_input_tokens: 1}};
  assert.throws(() => new ContextBuilder(tiny, () => {}).project(transcript()), /overflow/);
});
