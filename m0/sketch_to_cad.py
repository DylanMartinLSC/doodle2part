"""Sketch image -> CadQuery script via a local vision model (Ollama), with a retry loop.

    python sketch_to_cad.py sketch.png out_dir [--model qwen3-vl:8b-instruct] [--tries 5]
"""

import argparse
import base64
import json
import re
import time
from pathlib import Path

import requests

from cad_runner import run

OLLAMA = "http://127.0.0.1:11434/api/chat"
EXAMPLE = (Path(__file__).parent / "examples" / "l_bracket.py").read_text(encoding="utf-8")

SYSTEM = f"""You turn hand-drawn sketches of mechanical parts into CadQuery Python scripts.

Rules:
- Output ONLY one ```python code block, nothing else.
- `cq` is already imported. Do not import anything.
- First line: `PARAMS = {{...}}` with every dimension as a float in millimetres, named descriptively.
- Read dimensions from labels in the sketch; estimate unlabeled ones from proportions.
- Use only values from PARAMS (via `p = PARAMS`), never hard-coded numbers for dimensions.
- The final solid must be assigned to `result`.
- One single solid part. Prefer simple operations: box, rect/circle + extrude, hole, cboreHole, fillet, chamfer.
- Hole and feature positions are dimensions too: put insets/spacings in PARAMS.
- For repeated features use one call with `.pushPoints([...])` or `.rect(w, h, forConstruction=True).vertices()`
  on a single workplane, then `.hole(d)` once. Never call `.center()` repeatedly to place copies.

Example of the expected style:
```python
{EXAMPLE.strip()}
```"""


def extract_code(text):
    m = re.search(r"```(?:python)?\s*\n(.*?)```", text, re.S)
    return (m.group(1) if m else text).strip() + "\n"


def chat(model, messages):
    r = requests.post(OLLAMA, json={"model": model, "messages": messages, "stream": False,
                                    "options": {"temperature": 0.2, "num_ctx": 8192}}, timeout=600)
    r.raise_for_status()
    return r.json()["message"]["content"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sketch")
    ap.add_argument("out_dir")
    ap.add_argument("--model", default="qwen3-vl:8b-instruct")
    ap.add_argument("--tries", type=int, default=5)
    args = ap.parse_args()

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    img = base64.b64encode(Path(args.sketch).read_bytes()).decode()
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": "Write the CadQuery script for this part.", "images": [img]},
    ]

    log = []
    for attempt in range(1, args.tries + 1):
        t0 = time.perf_counter()
        reply = chat(args.model, messages)
        llm_s = round(time.perf_counter() - t0, 1)
        code = extract_code(reply)
        script = out / f"attempt{attempt}.py"
        script.write_text(code, encoding="utf-8")
        res = run(script, out / f"attempt{attempt}")
        log.append({"attempt": attempt, "llm_seconds": llm_s, **res})
        print(json.dumps(log[-1]))
        if res["ok"]:
            break
        # Feed the failure back so the model can fix its own script.
        messages += [
            {"role": "assistant", "content": reply},
            {"role": "user", "content": f"That script failed:\n{res['error']}\nFix it and output the full corrected script."},
        ]

    (out / "log.json").write_text(json.dumps(log, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
