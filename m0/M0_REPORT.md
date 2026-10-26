# M0 feasibility report — 2026-10-25

Machine: RTX 3090 24GB, Windows 11, driver 595.95. Everything ran **natively on Windows** — no WSL2.

## Verdict

| Piece | Result | Decision |
|---|---|---|
| TRELLIS (mesh mode) | ✅ Works natively. 12.5s per model, 10.4 GB peak VRAM | **Go** with TRELLIS |
| CadQuery export | ✅ STL / STEP / GLB, param overrides work | **Go** |
| Qwen3-VL 8B → CadQuery | ⚠️ Scripts run, but geometry is often wrong | **Go, with changes** (see below) |

## TRELLIS (mesh mode)

- Env: `.venv` — Python 3.11, torch 2.5.1+cu124, xformers 0.0.28.post3, spconv-cu124 2.3.8.
- `ATTN_BACKEND=xformers` (no flash-attn on Windows), `SPCONV_ALGO=native`.
- **No CUDA toolkit needed for geometry.** `kaolin` is only used for an input assert in FlexiCubes,
  so `trellis_test.py` stubs it. `nvdiffrast` / `diff_gaussian_rasterization` are only needed for
  texture baking, which this path skips.
- Output: raw FlexiCubes mesh with **vertex colours** (no baked texture). Dragon example:
  290,917 verts / 581,796 faces, 11.6 MB GLB, colours look right (`out/trellis/dragon_preview.png`).
- Timings: generate 12.5s; first load 132s (included ~3.5 GB of downloads — warm load will be much less).

**Follow-ups for M1**
- Decimate the mesh (~580k faces is too heavy for the browser); target ~50–100k.
- Check orientation in a real glTF viewer (the Z-up → Y-up rotation in `trellis_test.py` is unverified).
- Baked textures would need the CUDA toolkit to compile nvdiffrast + diff-gaussian-rasterization.
  Vertex colours are probably good enough for v0.1; decide after seeing it in the viewer.
- Install `hf_xet` for faster Hugging Face downloads.

## CadQuery

- Separate env `.venv-cad` (keeps OCP/VTK away from the torch env). `cad_runner.py` runs a script in
  a subprocess with a timeout, validates the solid, exports STL/STEP/GLB, returns bbox + volume.
- L-bracket example: default and overridden params both correct.
- **~2.5s per run, almost all of it `import cadquery`.** M4's <1s slider target needs a warm worker
  process that keeps CadQuery imported and executes scripts on request.

## Qwen3-VL 8B → CadQuery

Test sketch: 120×80×6 plate, 4× M6 corner holes, 30 mm centre hole (`out/sketch_plate.png`).

| Run | Model | Attempts | LLM time | Runs? | Correct? |
|---|---|---|---|---|---|
| 1 | `qwen3-vl:8b-instruct` | 1 | 11.9s | ✅ | ❌ all 4 M6 holes stacked on one corner |
| 2 | same, prompt tightened (pushPoints rule) | 1 | 6.6s | ✅ | ❌ ignored the rule; centre hole also moved to the corner |
| 3 | `qwen3-vl:8b` (thinking) | 5 | ~62s each | ❌ | Empty replies — output goes to the thinking field. Don't use. |

Dimensions (120 / 80 / 6 / 30 / M6) were read correctly every time. **Placement** is the failure:
the model copies the few-shot example's `.center()` chaining instead of following rules.

**Key finding: "runs" ≠ "correct".** The retry loop only catches crashes, not wrong geometry.

**Changes for M3**
1. **Few-shot examples that show the right patterns** (pushPoints, rectangular hole arrays,
   construction rects). The model imitates examples far more than it follows rules.
2. **Geometric check:** render the solid's top/side silhouette and compare against the sketch
   (IoU on a binarised image), and check hole counts. Feed mismatches back like errors.
3. **Try a bigger model** when CAD mode is active alone: Qwen3-VL 32B at Q4 (~20 GB) fits on the
   3090 if TRELLIS is unloaded — that's already the plan's load-one-model-at-a-time approach.
4. Build the ~20-sketch eval set early (M3, not M5), so prompt changes are measured.

## Files

- `cad_runner.py` — sandboxed CadQuery runner (reusable in M3)
- `sketch_to_cad.py` — Ollama vision → CadQuery with retry loop
- `make_sketch.py` — generates the test sketch
- `trellis_test.py` — TRELLIS image → vertex-coloured GLB on native Windows
- `render_preview.py` — GLB → PNG preview
- `examples/l_bracket.py` — few-shot example / CadQuery smoke test
- `out/` — generated artifacts (gitignored)
