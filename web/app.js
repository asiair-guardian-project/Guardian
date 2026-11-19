"use strict";
// Everything is written with textContent: log lines and monitor text are never
// treated as HTML.
const STALE_AFTER_MS = 20000;
const OBSERVATION_STALE_MS = 30000;
let lastGoodStatus = 0;

const $ = (id) => document.getElementById(id);
const set = (id, text) => { $(id).textContent = text; };
function show(id, text) {
  const el = $(id);
  el.hidden = !text;
  el.textContent = text || "";
}

async function getJSON(url, ms) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), ms);
  try {
    const response = await fetch(url, { cache: "no-store", signal: controller.signal });
    if (!response.ok) throw new Error(String(response.status));
    return await response.json();
  } finally {
    clearTimeout(timer);
  }
}

function banner(kind, text) {
  const el = $("banner");
  el.className = "banner " + kind;
  el.textContent = text;
}

function render(status) {
  const contact = status && status.connected === true;
  const stale = !contact || Date.now() - lastGoodStatus > STALE_AFTER_MS;
  $("panel").classList.toggle("stale", stale);
  if (!contact) {
    banner("bad", "NO CONTACT WITH THE MONITOR — protection status unknown");
    for (const id of ["session", "roof", "controller", "hardware", "arm", "observed"]) set(id, "–");
    show("armreason", ""); show("recovery", ""); show("incident", "");
    return;
  }
  const eq = status.equipment || null;
  set("session", status.session || "Unknown");
  set("roof", eq ? eq.roof : "No recent observation");
  set("controller", eq ? eq.controller : "–");
  set("hardware", status.hardware_execution_enabled
    ? "ENABLED (needs ARM)" : "DISABLED (watching only)");
  set("arm", status.armed ? "ARMED" : "DISARMED");
  show("armreason", !status.armed && status.arm_unavailable_reason
    ? "ARM unavailable: " + status.arm_unavailable_reason : "");
  show("recovery", status.recovery_reason ? "Recovery blocked: " + status.recovery_reason : "");
  if (status.incident_active) {
    const left = (status.unresolved_actions || []).join(", ");
    show("incident", "PROTECTION INCIDENT — " +
      (status.acknowledged ? "acknowledged" : "awaiting acknowledgment") +
      (left ? ". Unresolved: " + left : ""));
  } else {
    show("incident", "");
  }
  let note = "Updated " + new Date().toLocaleTimeString();
  let observationOld = false;
  if (eq && eq.observed_at_utc) {
    const age = Date.now() - Date.parse(eq.observed_at_utc);
    if (Number.isFinite(age) && age > OBSERVATION_STALE_MS) {
      observationOld = true;
      note += " · last equipment reading is " + Math.round(age / 1000) + " s old";
    }
  }
  set("observed", note);
  if (status.incident_active) banner("bad", "PROTECTION INCIDENT — see below");
  else if (observationOld || !eq) banner("warn", "Monitor reachable, but equipment readings are not current");
  else if (status.armed) banner("good", "Monitor running · ARMED");
  else banner("good", "Monitor running · " + (status.hardware_execution_enabled ? "disarmed" : "watching only"));
}

async function pollStatus() {
  try {
    const status = await getJSON("/api/status", 4000);
    if (status && status.connected === true) lastGoodStatus = Date.now();
    render(status);
  } catch (error) {
    render({ connected: false });
  }
}

async function pollText() {
  try {
    const events = await getJSON("/api/events", 4000);
    set("events", events.lines.length ? events.lines.join("\n") : "No events yet.");
    const nights = await getJSON("/api/nights", 4000);
    set("nights", nights.text || "No nights yet.");
  } catch (error) {
    set("events", "Could not load the event log.");
  }
}

pollStatus(); pollText();
setInterval(pollStatus, 5000);
setInterval(pollText, 30000);
