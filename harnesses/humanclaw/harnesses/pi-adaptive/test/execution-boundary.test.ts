import test from "node:test";
import assert from "node:assert/strict";
import { ExecutionBoundary } from "../src/execution-boundary.ts";

test("same-turn work cannot claim an unseen post-action frame", () => {
  const b = new ExecutionBoundary(), turn = {};
  assert.equal(b.admit(turn, "adaptive__memory", {}), undefined);
  assert.equal(b.admit(turn, "adaptive__execute", {request_id: "a", evidence: ["o0"]}), undefined);
  assert.match(b.admit(turn, "adaptive__execute", {request_id: "b", evidence: ["o1"]})!, /new model request/);
  assert.match(b.admit(turn, "adaptive__memory", {completion: "supported"})!, /new model request/);
  assert.equal(b.admit({}, "adaptive__execute", {request_id: "b", evidence: ["o1"]}), undefined);
});
test("identical retries and receipt recovery stay available", () => {
  const b = new ExecutionBoundary(), turn = {};
  b.admit(turn, "adaptive__execute", {request_id: "a"});
  assert.equal(b.admit(turn, "adaptive__execute", {request_id: "a"}), undefined);
  assert.equal(b.admit(turn, "adaptive__receipt", {request_id: "a"}), undefined);
});
test("adapter probes also require a new model turn before using their result", () => {
  const boundary = new ExecutionBoundary(), turn = {};
  const probe = {action: "probe", arguments: {id: "binding", request: {request_id: "p1"}}};
  assert.equal(boundary.admit(turn, "adaptive__adapter", probe), undefined);
  assert.equal(boundary.admit(turn, "adaptive__adapter", probe), undefined);
  assert.match(boundary.admit(turn, "adaptive__memory", {update: {completion: "supported"}})!, /new model request/);
  assert.match(boundary.admit(turn, "adaptive__adapter", {action: "register"})!, /new model request/);
  assert.equal(boundary.admit({}, "adaptive__adapter", {action: "register"}), undefined);
});
