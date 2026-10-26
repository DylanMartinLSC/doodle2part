import { createViewer } from "/static/viewer.js";

const $ = (id) => document.getElementById(id);
const make = (tag, props) => Object.assign(document.createElement(tag), props);
const canvas = $("sketch");
const ctx = canvas.getContext("2d", { willReadFrequently: true });
const strokeCanvas = $("stroke");
const strokeCtx = strokeCanvas.getContext("2d");
const stage = $("sketch-stage");
const output = $("output");
const status = $("status");
const W = canvas.width;
const H = canvas.height;
const MODEL_SIZE = 512;  // frames are downscaled to this before sending
const BRUSH_SCALE = W / MODEL_SIZE;  // brush sizes are in model pixels

const SWATCHES = ["#000000", "#ffffff", "#1e3a8a", "#38bdf8", "#16a34a", "#facc15", "#f97316", "#dc2626", "#7c3aed", "#78350f"];
const TOOL_KEYS = { b: "brush", e: "eraser" };
const SETTINGS = ["prompt", "strength", "size", "color"];  // inputs remembered between visits
const SETTINGS_KEY = "doodle2part.settings";
const UNDO_MAX = 50;

let tool = "brush";
let seed = randomSeed();

function randomSeed() { return Math.floor(Math.random() * 2 ** 31); }

// ---- settings persistence --------------------------------------------------

function saveSettings() {
  try {
    const values = Object.fromEntries(SETTINGS.map((id) => [id, $(id).value]));
    localStorage.setItem(SETTINGS_KEY, JSON.stringify({ ...values, seed }));
  } catch {}
}

function loadSettings() {
  try {
    const s = JSON.parse(localStorage.getItem(SETTINGS_KEY)) || {};
    for (const id of SETTINGS) if (s[id] != null) $(id).value = s[id];
    if (Number.isInteger(s.seed)) seed = s.seed;
  } catch {}
}

// ---- undo / redo -----------------------------------------------------------

const undoStack = [];
const redoStack = [];
const snapshot = () => ctx.getImageData(0, 0, W, H);

function saveHistory() {
  undoStack.push(snapshot());
  if (undoStack.length > UNDO_MAX) undoStack.shift();
  redoStack.length = 0;
}

// Apply a whole-canvas change as one undoable step.
function edit(draw) {
  saveHistory();
  draw();
  requestFrame();
}

// Undo and redo are mirror images: pop a snapshot from one stack, push the current canvas onto the other.
function restore(from, to) {
  if (!from.length) return;
  to.push(snapshot());
  ctx.putImageData(from.pop(), 0, 0);
  requestFrame();
}
const undo = () => restore(undoStack, redoStack);
const redo = () => restore(redoStack, undoStack);

// ---- drawing ---------------------------------------------------------------
// Strokes go on an overlay canvas and are merged on pointer-up, so the
// in-progress stroke can be composited into frames without committing it.

function resetCanvas() {
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, W, H);
}

function toCanvas(e) {
  const r = stage.getBoundingClientRect();
  return [(e.clientX - r.left) * (W / r.width), (e.clientY - r.top) * (H / r.height)];
}

let last = null;
let stroking = false;

stage.addEventListener("pointerdown", (e) => {
  if (e.button !== 0) return;
  try { stage.setPointerCapture(e.pointerId); } catch {}
  saveHistory();
  stroking = true;
  last = toCanvas(e);
  stroke(e, last);
});

stage.addEventListener("pointermove", (e) => {
  moveCursor(e);
  if (!stroking) return;
  // Coalesced events give smooth lines on fast pen/mouse movement.
  const events = e.getCoalescedEvents?.() ?? [];
  for (const ev of events.length ? events : [e]) stroke(ev, toCanvas(ev));
});

function endStroke() {
  if (!stroking) return;
  stroking = false;
  last = null;
  ctx.drawImage(strokeCanvas, 0, 0);
  strokeCtx.clearRect(0, 0, W, H);
  requestFrame();
}
stage.addEventListener("pointerup", endStroke);
stage.addEventListener("pointercancel", endStroke);

function stroke(e, point) {
  const pressure = e.pointerType === "pen" ? Math.max(e.pressure, 0.1) * 2 : 1;
  strokeCtx.strokeStyle = tool === "eraser" ? "#ffffff" : $("color").value;
  strokeCtx.lineWidth = $("size").value * BRUSH_SCALE * pressure;
  strokeCtx.lineCap = strokeCtx.lineJoin = "round";
  strokeCtx.beginPath();
  strokeCtx.moveTo(...last);
  strokeCtx.lineTo(...point);
  strokeCtx.stroke();
  last = point;
  requestFrame();
}

// The canvas as the model should see it: downscaled, including any in-progress stroke.
const frameCanvas = make("canvas", { width: MODEL_SIZE, height: MODEL_SIZE });
const frameCtx = frameCanvas.getContext("2d");

function composite() {
  frameCtx.drawImage(canvas, 0, 0, MODEL_SIZE, MODEL_SIZE);
  if (stroking) frameCtx.drawImage(strokeCanvas, 0, 0, MODEL_SIZE, MODEL_SIZE);
  return frameCanvas;
}

// ---- brush cursor ----------------------------------------------------------

const cursor = $("cursor");

function moveCursor(e) {
  const r = stage.getBoundingClientRect();
  const d = $("size").value * BRUSH_SCALE * (r.width / W);
  Object.assign(cursor.style, {
    display: "block",
    left: `${e.clientX - r.left}px`,
    top: `${e.clientY - r.top}px`,
    width: `${d}px`,
    height: `${d}px`,
  });
}
stage.addEventListener("pointerleave", () => (cursor.style.display = "none"));

// ---- paste / drop an image -------------------------------------------------

function placeImage(blob) {
  if (!blob?.type.startsWith("image/")) return;
  const img = new Image();
  img.onload = () => edit(() => {
    resetCanvas();
    // Contain-fit: the whole object should stay in frame for the 3D step.
    const s = Math.min(W / img.width, H / img.height);
    ctx.drawImage(img, (W - img.width * s) / 2, (H - img.height * s) / 2, img.width * s, img.height * s);
    URL.revokeObjectURL(img.src);
  });
  img.src = URL.createObjectURL(blob);
}

document.addEventListener("paste", (e) => {
  if (e.target === $("prompt") && !e.clipboardData.files.length) return;
  const file = [...e.clipboardData.files].find((f) => f.type.startsWith("image/"));
  if (file) { e.preventDefault(); placeImage(file); }
});

stage.addEventListener("dragover", (e) => { e.preventDefault(); stage.classList.add("dragover"); });
stage.addEventListener("dragleave", () => stage.classList.remove("dragover"));
stage.addEventListener("drop", (e) => {
  e.preventDefault();
  stage.classList.remove("dragover");
  placeImage(e.dataTransfer.files[0]);
});

// ---- toolbar ---------------------------------------------------------------

function setTool(name) {
  tool = name;
  for (const t of Object.values(TOOL_KEYS)) $(t).classList.toggle("active", t === name);
}

function setColor(hex) {
  $("color").value = hex;
  setTool("brush");
  saveSettings();
}

function setSeed(value) {
  seed = value;
  $("seed").value = seed;
  saveSettings();
  requestFrame();
}

for (const c of SWATCHES) {
  const swatch = make("div", { className: "swatch", title: c, onclick: () => setColor(c) });
  swatch.style.background = c;
  $("swatches").append(swatch);
}

for (const t of Object.values(TOOL_KEYS)) $(t).onclick = () => setTool(t);
$("clear").onclick = () => edit(resetCanvas);
$("undo").onclick = undo;
$("redo").onclick = redo;
$("reseed").onclick = () => setSeed(randomSeed());
$("seed").addEventListener("change", () => {
  const v = parseInt($("seed").value, 10);
  if (Number.isInteger(v) && v >= 0) setSeed(v); else $("seed").value = seed;
});
// Inputs that change the picture re-render; brush inputs only need saving.
for (const id of ["prompt", "strength"]) $(id).addEventListener("input", () => { saveSettings(); requestFrame(); });
for (const id of ["size", "color"]) $(id).addEventListener("input", saveSettings);

document.addEventListener("keydown", (e) => {
  const mod = e.ctrlKey || e.metaKey;
  const key = e.key.toLowerCase();
  if (mod && key === "enter") { e.preventDefault(); make3d(); return; }
  if (e.target.matches?.("input[type=text], input[type=number]")) return;
  if (mod && (key === "z" || key === "y")) { e.preventDefault(); key === "y" || e.shiftKey ? redo() : undo(); }
  else if (mod || e.altKey) return;
  else if (TOOL_KEYS[key]) setTool(TOOL_KEYS[key]);
  else if (key === "[" || key === "]") {
    const size = $("size");
    const next = key === "]" ? Math.ceil(size.value * 1.15 + 1) : Math.floor(size.value / 1.15 - 1);
    size.value = Math.min(size.max, Math.max(size.min, next));
    saveSettings();
  }
});

// ---- live preview streaming ------------------------------------------------
// At most one frame is in flight; changes made meanwhile set `dirty`, and the
// newest canvas is sent as soon as the previous result arrives.

let socket;
let inFlight = false;
let dirty = false;
let frameId = 0;

function connect() {
  socket = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws`);
  socket.onopen = () => { status.textContent = "ready"; inFlight = false; requestFrame(); };
  socket.onclose = () => { status.textContent = "reconnecting…"; setTimeout(connect, 1000); };
  socket.onmessage = (e) => {
    const msg = JSON.parse(e.data);
    inFlight = false;
    if (msg.error) {
      status.textContent = "error (see console)";
      console.error(msg.error);
    } else {
      output.src = msg.image;
      if (!making) status.textContent = `preview ${msg.ms} ms`;
    }
    if (dirty) sendFrame();
  };
}

function requestFrame() {
  dirty = true;
  if (!inFlight) sendFrame();
}

function sendFrame() {
  if (socket?.readyState !== WebSocket.OPEN) return;
  dirty = false;
  inFlight = true;
  socket.send(JSON.stringify({
    id: ++frameId,
    image: composite().toDataURL("image/png"),
    prompt: $("prompt").value,
    strength: parseFloat($("strength").value),
    seed,
  }));
}

// ---- 3D --------------------------------------------------------------------

const viewer = createViewer($("viewer"));
window.viewer = viewer;  // for scripted demos
let making = false;
let wireframe = false;

viewer.onSpinChange((on) => $("spin").classList.toggle("active", on));
$("spin").onclick = () => {
  const on = !$("spin").classList.contains("active");
  $("spin").classList.toggle("active", on);
  viewer.setSpin(on);
};
$("wireframe").onclick = () => {
  wireframe = !wireframe;
  $("wireframe").classList.toggle("active", wireframe);
  viewer.setWireframe(wireframe);
};
$("make3d").onclick = make3d;

async function showModel(result, thumb) {
  const { faces } = await viewer.load(result.glb);
  $("viewer-empty").hidden = true;
  $("download").href = result.glb;
  $("download").hidden = false;
  $("mesh-info").textContent = `${faces.toLocaleString()} faces · drag to orbit, scroll to zoom`;
  for (const t of $("history").children) t.classList.toggle("active", t === thumb);
}

async function make3d() {
  if (making || !output.src) return;
  making = true;
  $("make3d").disabled = true;
  $("loading").hidden = false;
  $("viewer-empty").hidden = true;
  const started = performance.now();
  const tick = setInterval(() => {
    $("loading-text").textContent = `Building 3D model… ${((performance.now() - started) / 1000).toFixed(0)}s`;
  }, 250);
  try {
    const res = await fetch("/make3d", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ image: output.src, seed }),
    });
    const result = await res.json();
    if (!res.ok) throw new Error(result.error || res.statusText);
    const thumb = make("div", { className: "thumb", title: `${$("prompt").value}\nseed ${seed}` });
    thumb.append(make("img", { src: result.thumb }));
    thumb.onclick = () => showModel(result, thumb);
    $("history").prepend(thumb);
    await showModel(result, thumb);
    status.textContent = `3D in ${(result.ms / 1000).toFixed(1)} s`;
  } catch (err) {
    status.textContent = "3D failed (see console)";
    console.error(err);
    $("viewer-empty").hidden = !$("download").hidden;  // bring the hint back if nothing is shown yet
  } finally {
    clearInterval(tick);
    $("loading").hidden = true;
    $("loading-text").textContent = "";
    $("make3d").disabled = false;
    making = false;
  }
}

loadSettings();
$("seed").value = seed;
resetCanvas();
connect();
