"""Run a CadQuery script in a subprocess and export STL / STEP / GLB.

The script must define `result` (a cq.Workplane or Shape). An optional `PARAMS`
dict at the top can be overridden with --params '{"width": 40}'.

    python cad_runner.py script.py out_dir [--params JSON] [--timeout 30]

Prints one JSON line: {"ok": true, "files": {...}, "seconds": ...} or {"ok": false, "error": ...}.
"""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

CHILD = r"""
import json, sys
import cadquery as cq
import trimesh

src, out_dir, params = sys.argv[1], sys.argv[2], json.loads(sys.argv[3])
ns = {"cq": cq, "__name__": "__cad__"}
code = open(src, encoding="utf-8").read()
# Let overrides win over the script's own PARAMS dict.
ns["__overrides__"] = params
code = code.replace("PARAMS = {", "PARAMS = __overrides__ or {", 1) if params else code
exec(compile(code, src, "exec"), ns)

result = ns.get("result")
if result is None:
    raise RuntimeError("script did not define `result`")
shape = result.val() if isinstance(result, cq.Workplane) else result
if not shape.isValid():
    raise RuntimeError("resulting shape is not valid")
if shape.Volume() <= 0:
    raise RuntimeError("resulting shape has zero volume")

stl, step, glb = f"{out_dir}/part.stl", f"{out_dir}/part.step", f"{out_dir}/part.glb"
cq.exporters.export(shape, stl, tolerance=0.05, angularTolerance=0.1)
cq.exporters.export(shape, step)
trimesh.load(stl).export(glb)
bb = shape.BoundingBox()
print(json.dumps({"stl": stl, "step": step, "glb": glb,
                  "bbox": [round(bb.xlen, 2), round(bb.ylen, 2), round(bb.zlen, 2)],
                  "volume": round(shape.Volume(), 2)}))
"""


def run(script, out_dir, params=None, timeout=30):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    start = time.perf_counter()
    try:
        proc = subprocess.run(
            [sys.executable, "-I", "-c", CHILD, str(script), str(out_dir), json.dumps(params or {})],
            capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"timed out after {timeout}s"}
    seconds = round(time.perf_counter() - start, 2)
    if proc.returncode != 0:
        # The last lines of the traceback are what the LLM needs to fix the script.
        return {"ok": False, "error": "\n".join(proc.stderr.strip().splitlines()[-8:]), "seconds": seconds}
    return {"ok": True, "files": json.loads(proc.stdout.strip().splitlines()[-1]), "seconds": seconds}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("script")
    ap.add_argument("out_dir")
    ap.add_argument("--params", default="{}")
    ap.add_argument("--timeout", type=int, default=30)
    args = ap.parse_args()
    print(json.dumps(run(args.script, args.out_dir, json.loads(args.params), args.timeout)))


if __name__ == "__main__":
    main()
