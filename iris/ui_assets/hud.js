"use strict";
// One bounded, same-origin poll at a time. No caption storage or logging.
(() => {
  const view = document.getElementById("voice-view");
  const user = document.getElementById("user-speech");
  const reply = document.getElementById("iris-response");
  const stateLabel = document.getElementById("voice-state");
  const hint = document.getElementById("voice-hint");
  const input = document.getElementById("input-label");
  const hints = {
    idle: "Ready · microphone inactive",
    listening: "Listening to this one request",
    thinking: "Processing your request · preparing the reply",
    speaking: "Playing the reply",
    muted: "Voice is muted",
    error: "Voice turn failed. Check the terminal for safe diagnostics."
  };
  let active = true;
  let timer;
  let controller;
  function text(element, value) {
    if (element.textContent !== value) element.textContent = value;
  }
  function render(event) {
    const state = Object.hasOwn(hints, event.state) ? event.state : "error";
    view.dataset.state = state;
    text(stateLabel, state.toUpperCase());
    text(hint, hints[state]);
    text(input, state === "listening" ? "Capture active" : "Not recording");
    // Plain text, never innerHTML; canonical IRIS text is not rewritten for TTS.
    text(user, typeof event.user_speech === "string" ? event.user_speech.slice(0, 4000) : "");
    text(reply, typeof event.response === "string" ? event.response.slice(0, 8000) : "");
  }
  async function poll() {
    controller = new AbortController();
    const deadline = setTimeout(() => controller.abort(), 2000);
    try {
      const response = await fetch("/api/conversation", {
        cache: "no-store", credentials: "same-origin", signal: controller.signal
      });
      if (!response.ok) throw new Error("HUD unavailable");
      const event = await response.json();
      if (active) render(event);
    } catch (_) {
      if (active) {
        render({state: "error"});
        text(hint, "Session unavailable · captions cleared");
      }
    } finally {
      clearTimeout(deadline);
      if (active) timer = setTimeout(poll, 100);
    }
  }
  window.addEventListener("pagehide", () => {
    active = false;
    clearTimeout(timer);
    if (controller) controller.abort();
    render({state: "idle"});
  });
  window.addEventListener("pageshow", () => {
    if (!active) { active = true; poll(); }
  });
  poll();
})();
