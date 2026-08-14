import assert from "node:assert/strict";
import { duplicateKeys } from "../zotero-plugin/src/duplicateSets.js";
import { EventQueue } from "../zotero-plugin/src/eventQueue.js";
import { makeRequest } from "../zotero-plugin/src/request.js";

assert.deepEqual([...duplicateKeys([["A", "B"], ["B", "C"]])].sort(), ["A", "B", "C"]);

const timers = [];
const queue = new EventQueue({
  delayMs: 15,
  setTimeoutFn: (callback) => { timers.push(callback); return callback; },
  clearTimeoutFn: () => {},
  onQuiet: async (keys) => { calls.push(keys); await Promise.resolve(); }
});
const calls = [];
queue.addOne("A");
queue.addOne("B");
assert.equal(timers.length, 2);
await timers.at(-1)();
assert.deepEqual(calls, [["A", "B"]]);

let release;
const runningCalls = [];
const runningTimers = [];
const runningQueue = new EventQueue({
  delayMs: 1,
  setTimeoutFn: (callback) => { runningTimers.push(callback); return callback; },
  clearTimeoutFn: () => {},
  onQuiet: async (keys) => {
    runningCalls.push(keys);
    await new Promise((resolve) => { release = resolve; });
  }
});
runningQueue.addOne("first");
const firstRun = runningTimers[0]();
await Promise.resolve();
runningQueue.addOne("second");
release();
await firstRun;
await Promise.resolve();
await Promise.resolve();
assert.equal(runningCalls.length, 1);
assert.equal(runningTimers.length, 3);
const secondRun = runningTimers.at(-1)();
await Promise.resolve();
release();
await secondRun;
assert.deepEqual(runningCalls, [["first"], ["second"]]);

const request = makeRequest({ requestId: "r", generatedAt: "now", libraryId: "1", generation: "2", candidates: [
  { parent_item_key: "P", parent_item_version: 1, attachment_key: "A", attachment_version: 2, eligible: true }
]});
assert.equal(request.schema_version, 1);
assert.equal(request.candidates[0].eligible, true);
console.log("plugin tests passed");
