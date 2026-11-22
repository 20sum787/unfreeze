const byId = (id) => document.getElementById(id);
const form = byId("access");

function show(id, label, active = false) {
  const element = byId(id);
  element.textContent = label;
  element.dataset.active = String(active);
}

function unavailable(message) {
  for (const id of ["freeze", "speaker", "buzzer", "vibro"]) show(id, "—");
  byId("status").textContent = message;
}

function hardware(id, output, supported) {
  if (output?.state === "applied") {
    const labels = {"freeze pulses 5 s": "Freeze pulses · 5 s", "sustained freeze": "Freeze alarm · 5 s"};
    show(id, labels[output.reason] || "Command accepted", true);
  }
  else if (output?.state === "failed") show(id, "Command failed");
  else show(id, supported ? "Idle" : "Unavailable");
}

function render(s) {
  show("freeze", Number.isFinite(s.freeze) ? s.freeze.toFixed(3)
    : s.session === "ACTIVE" ? "Waiting for a fresh score" : "—");
  if (s.audio?.output === "phone_audio" && s.audio.state === "started")
    show("speaker", "Playback confirmed", true);
  else show("speaker", s.phonePending ? "Awaiting playback" : "Idle");
  hardware("buzzer", s.audio?.output === "buzzer" ? s.audio : null, s.buzzerSupported);
  hardware("vibro", s.haptics, s.hapticsSupported);
  const phase = {IDLE: "Session idle", ACTIVE: "Session active", FAULT: "Session fault"};
  byId("status").textContent = [phase[s.session] || s.session, s.vision].filter(Boolean).join(" · ");
}

async function poll() {
  try {
    const response = await fetch("/v1/preview/state", {
      cache: "no-store", signal: AbortSignal.timeout(2500),
    });
    if (response.status === 401) {
      unavailable("Enter the board pairing code to view status. The phone can continue controlling the session.");
      form.hidden = false;
      return;
    }
    if (!response.ok) throw Error();
    render(await response.json());
  } catch {
    unavailable("Connection lost. Reconnecting…");
  }
  setTimeout(poll, document.hidden ? 2000 : 400);
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = form.querySelector("button");
  if (button.disabled) return;
  button.disabled = true;
  try {
    const response = await fetch("/v1/preview/access", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({code: form.elements.code.value}), signal: AbortSignal.timeout(4000),
    });
    if (!response.ok) {
      byId("status").textContent = response.status === 429 ? "Try again in 30 seconds."
        : response.status === 401 ? "Check the pairing code and try again." : "Verification failed. Try again.";
      return;
    }
    form.reset();
    form.hidden = true;
    await poll();
  } catch {
    unavailable("Could not reach the controller. Try again.");
  } finally {
    button.disabled = false;
  }
});

poll();
