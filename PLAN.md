# Doodle2Part — Plan

Draw in the browser. Organic shapes come back as a textured 3D mesh; mechanical parts come back
as parametric CAD with live sliders. Fully offline, native Windows, one RTX 3090 (24GB).

## Decisions

- **Fully offline.** No API keys, no cloud. Sketches never leave the machine.
- **Native Windows first.** WSL2 only as a last resort.
- **CAD vision model:** Qwen3-VL 8B via Ollama (`qwen3-vl:8b-instruct`, already pulled).
- **Mesh model:** TRELLIS, behind an interface so TRELLIS.2 / Hunyuan3D-2 mini can be swapped in.
  M0 confirmed it runs natively on Windows (vertex colours, no CUDA toolkit) — see `m0/M0_REPORT.md`.
- **Separate repo** from SketchLive; reuse its canvas, WebSocket loop and mock-generator pattern.

## Architecture

```
Browser (canvas + three.js viewer)
   │  WebSocket: strokes, mode, params ⇄ progress, results
   ▼
FastAPI server
   ├── Live preview: SD-Turbo img2img (from SketchLive)
   ├── Mesh mode: preview image → background removal → TRELLIS → .glb
   └── CAD mode:  sketch → Qwen3-VL → CadQuery script
                     → sandboxed subprocess (retry loop) → STL/STEP → .glb
```

Mode is a manual toggle. Auto-detecting the mode is a stretch goal.

## Shared foundation

- `Generator3D` interface plus a mock that returns a sample `.glb`, so frontend work never waits on the GPU.
- three.js viewer (or `<model-viewer>`): orbit, wireframe toggle, download buttons.
- History panel: each result keeps its sketch, output and (CAD mode) script.
- VRAM: TRELLIS and Qwen3-VL don't comfortably share 24GB, so load each model when its mode is
  active and unload the other. Mode switches cost a few seconds; document it.

## Mode A — Mesh

1. "Make 3D" freezes the current SD-Turbo preview as the reference image.
2. Background removal (rembg or TRELLIS's own preprocessing).
3. TRELLIS → textured `.glb`. Expect ~20–60s; stream progress over the WebSocket.

## Mode B — CAD

1. **Codegen:** sketch image → Qwen3-VL. Prompt requires a CadQuery script with `PARAMS = {...}`
   (mm) at the top and a `result` solid at the end. Include a few example scripts in the prompt.
2. **Sandboxed exec:** subprocess, timeout, restricted imports. Generated code is untrusted.
3. **Retry loop:** on exception, empty or invalid solid, feed the traceback back. Up to 5 attempts.
4. **Parametric sliders:** parse `PARAMS` with `ast`, render a slider per value. Sliders re-run the
   script with new values — no LLM call, so it's fast and deterministic.
5. **Export:** STEP + STL for download, GLB (via trimesh) for the viewer.
6. *Stretch:* render the solid, show it next to the sketch to the model, let it self-correct.

Scope for v1: single-part prismatic parts (extrude, holes, fillets). No assemblies.

## Milestones

| # | Milestone | Done when |
|---|---|---|
| M0 | Feasibility spike | TRELLIS produces a `.glb` on native Windows; CadQuery script → STL/GLB; Qwen3-VL turns one sketch into a CadQuery script that runs. Report: timings, peak VRAM, go/no-go per piece. |
| M1 | Mesh mode end to end | Sketch → preview → 3D model you can orbit in the browser |
| M2 | **Ship v0.1** | README, demo GIF, install steps. Portfolio-ready; a valid stopping point. |
| M3 | CAD codegen | Sketch → working solid, with retries and sandboxed exec |
| M4 | Parametric sliders | Dragging a slider rebuilds the model in under 1s |
| M5 | Polish + eval | STEP export, example gallery, success rate on ~20 test sketches in the README |

## Risks

- **TRELLIS on native Windows** (biggest). Needs spconv, kaolin, nvdiffrast, flash-attn — Linux-first.
  Fallback order: community Windows wheels → Hunyuan3D-2 mini → WSL2.
- **Local model writes broken CadQuery.** Mitigated by few-shot examples, the retry loop, and the
  eval set (the published success rate is itself a talking point).
- **CAD scope creep.** Hold to single prismatic parts for v1.
- **Licenses.** Check TRELLIS / Hunyuan3D terms before publishing.

## Environment notes (2026-10-25)

- RTX 3090 24GB, driver 595.95 (CUDA 13.2), ~1TB free on C:.
- Installed Pythons are 3.13 and 3.8; use `uv` to get a 3.11 venv (best wheel coverage for TRELLIS deps).
- No CUDA toolkit (`nvcc`) installed — needed only if a dependency must build from source.
- Visual Studio 2019/2022 present (MSVC for native extensions).
- Ollama installed with `qwen3-vl:8b` and `qwen3-vl:8b-instruct`.
