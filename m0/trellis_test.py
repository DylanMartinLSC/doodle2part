"""TRELLIS image -> mesh on native Windows, without the CUDA extensions that need nvcc.

kaolin (only check_tensor is used) and nvdiffrast (only needed for texture baking) are stubbed,
so this exports the raw FlexiCubes mesh with vertex colours instead of a baked-texture GLB.

    python trellis_test.py image.png out.glb
"""

import os
import sys
import time
import types
from pathlib import Path

os.environ.setdefault("ATTN_BACKEND", "xformers")  # flash-attn has no Windows wheels
os.environ.setdefault("SPCONV_ALGO", "native")      # skip spconv's slow first-run autotune

# Stub kaolin.utils.testing.check_tensor (FlexiCubes only calls it for input asserts).
kaolin = types.ModuleType("kaolin")
kaolin.utils = types.ModuleType("kaolin.utils")
kaolin.utils.testing = types.ModuleType("kaolin.utils.testing")
kaolin.utils.testing.check_tensor = lambda *a, **k: True
sys.modules.update({"kaolin": kaolin, "kaolin.utils": kaolin.utils, "kaolin.utils.testing": kaolin.utils.testing})

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "third_party" / "TRELLIS"))

import numpy as np  # noqa: E402
import torch  # noqa: E402
import trimesh  # noqa: E402
from PIL import Image  # noqa: E402
from trellis.pipelines import TrellisImageTo3DPipeline  # noqa: E402


def main():
    image_path, out_path = sys.argv[1], sys.argv[2]
    t0 = time.perf_counter()
    pipe = TrellisImageTo3DPipeline.from_pretrained("microsoft/TRELLIS-image-large")
    pipe.cuda()
    load_s = time.perf_counter() - t0

    torch.cuda.reset_peak_memory_stats()
    t1 = time.perf_counter()
    out = pipe.run(Image.open(image_path), seed=1, formats=["mesh"])
    gen_s = time.perf_counter() - t1

    mesh = out["mesh"][0]
    verts = mesh.vertices.detach().cpu().numpy()
    faces = mesh.faces.detach().cpu().numpy()
    colors = None
    if mesh.vertex_attrs is not None and mesh.vertex_attrs.shape[-1] >= 3:
        colors = (mesh.vertex_attrs[:, :3].clamp(0, 1).detach().cpu().numpy() * 255).astype(np.uint8)
    # TRELLIS is Z-up; glTF viewers expect Y-up.
    verts = verts @ np.array([[1, 0, 0], [0, 0, -1], [0, 1, 0]], dtype=verts.dtype)
    trimesh.Trimesh(verts, faces, vertex_colors=colors, process=False).export(out_path)

    print(f"load {load_s:.1f}s  generate {gen_s:.1f}s  peak VRAM {torch.cuda.max_memory_allocated() / 2**30:.1f} GB  "
          f"verts {len(verts)}  faces {len(faces)}  colors {'yes' if colors is not None else 'no'}")


if __name__ == "__main__":
    main()
