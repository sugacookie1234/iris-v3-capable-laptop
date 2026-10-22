// Execute the shipped browser controller against a tiny DOM/fetch boundary.
// No browser, microphone, network, storage, or third-party JS packages required.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const elements = new Map();
const listeners = new Map();
const timers = new Map();
let timerId = 0;
let next = {state: "idle", user_speech: "", response: ""};
let failed = false;
let calls = 0;
const context = {
  AbortController,
  document: {getElementById(id) {
    if (!elements.has(id)) elements.set(id, {textContent: "", dataset: {}});
    return elements.get(id);
  }},
  window: {addEventListener: (name, fn) => listeners.set(name, fn)},
  setTimeout(fn, delay) { timers.set(++timerId, {fn, delay}); return timerId; },
  clearTimeout(id) { timers.delete(id); },
  async fetch(url, options) {
    calls++;
    assert.equal(url, "/api/conversation");
    assert.equal(options.cache, "no-store");
    if (failed) throw new Error("private-error-that-must-not-render");
    return {ok: true, async json() { return next; }};
  }
};
const flush = () => new Promise(resolve => setImmediate(resolve));
async function advance(event) {
  next = event;
  const poll = [...timers].find(([, value]) => value.delay === 100);
  assert.ok(poll, "poll should be scheduled after previous completion");
  timers.delete(poll[0]);
  await poll[1].fn();
}
const el = id => elements.get(id);
(async () => {
  vm.runInNewContext(fs.readFileSync(process.argv[2], "utf8"), context);
  await flush();
  assert.equal(el("voice-view").dataset.state, "idle");
  assert.equal(el("input-label").textContent, "Not recording");
  for (const state of ["listening", "thinking", "speaking", "idle", "muted", "error"]) {
    await advance({state, user_speech: "Synthetic 1/2?", response: "IRIS <literal> 1/2"});
    assert.equal(el("voice-view").dataset.state, state);
    assert.equal(el("voice-state").textContent, state.toUpperCase());
    assert.equal(el("iris-response").textContent, "IRIS <literal> 1/2");
    assert.equal(el("input-label").textContent, state === "listening" ? "Capture active" : "Not recording");
  }
  failed = true;
  await advance({});
  assert.equal(el("iris-response").textContent, "");
  assert.equal(el("user-speech").textContent, "");
  assert.equal(el("voice-hint").textContent, "Session unavailable · captions cleared");
  failed = false;
  await advance({state: "idle", response: "IRIS session-only reply"});
  listeners.get("pagehide")();
  assert.equal(el("iris-response").textContent, "");
  assert.equal(el("voice-view").dataset.state, "idle");
  assert.equal(timers.size, 0);
  const prior = calls;
  listeners.get("pageshow")();
  await flush();
  assert.equal(calls, prior + 1);
  listeners.get("pagehide")();
})().catch(() => { process.exitCode = 1; });
