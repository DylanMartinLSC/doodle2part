"""Image -> 3D mesh (GLB bytes).

TrellisMesh runs TRELLIS natively on Windows without the CUDA toolkit: kaolin is
stubbed (FlexiCubes only uses it for an input assert) and texture baking, which
needs nvdiffrast, is skipped. The mesh keeps TRELLIS's per-vertex colours.
"""

import io
import os
import sys
import time
import types
from pathlib import Path

import numpy as np
import trimesh

TRELLIS_DIR = Path(__file__).parent / "third_party" / "TRELLIS"
TRELLIS_REPO = "microsoft/TRELLIS-image-large"
# TRELLIS is Z-up; glTF is Y-up. (x, y, z) -> (x, z, -y)
Z_UP_TO_Y_UP = np.array([[1, 0, 0], [0, 0, -1], [0, 1, 0]], dtype=np.float32)


def to_glb(vertices, faces, colors=None):
    buf = io.BytesIO()
    trimesh.Trimesh(vertices, faces, vertex_colors=colors, process=False).export(buf, file_type="glb")
    return buf.getvalue()


def decimate(vertices, faces, colors, target_faces):
    """Quadric decimation that keeps vertex colours; TRELLIS meshes are ~600k faces, too heavy for a browser."""
    if len(faces) <= target_faces:
        return vertices, faces, colors
    import open3d as o3d

    m = o3d.geometry.TriangleMesh(o3d.utility.Vector3dVector(vertices.astype(np.float64)),
                                  o3d.utility.Vector3iVector(faces.astype(np.int32)))
    if colors is not None:
        m.vertex_colors = o3d.utility.Vector3dVector(colors[:, :3].astype(np.float64) / 255)
    m = m.simplify_quadric_decimation(target_number_of_triangles=target_faces)
    m.remove_unreferenced_vertices()
    out_colors = (np.asarray(m.vertex_colors) * 255).round().astype(np.uint8) if m.has_vertex_colors() else None
    return np.asarray(m.vertices, dtype=np.float32), np.asarray(m.triangles), out_colors


class MockMesh:
    """A coloured blob so the 3D viewer works without a GPU."""

    def __call__(self, image, seed, target_faces):
        time.sleep(1)
        sphere = trimesh.creation.icosphere(subdivisions=4)
        rng = np.random.default_rng(seed)
        sphere.vertices *= 1 + 0.15 * rng.standard_normal((1, 3))
        avg = np.asarray(image.resize((1, 1))).reshape(3)
        shade = (0.6 + 0.4 * (sphere.vertices[:, 1:2] + 1) / 2) * avg
        colors = np.hstack([shade.clip(0, 255), np.full((len(shade), 1), 255)]).astype(np.uint8)
        return to_glb(sphere.vertices, sphere.faces, colors), {"faces": len(sphere.faces)}


class TrellisMesh:
    def __init__(self):
        os.environ.setdefault("ATTN_BACKEND", "xformers")  # flash-attn has no Windows wheels
        os.environ.setdefault("SPCONV_ALGO", "native")      # skip spconv's slow first-run autotune
        kaolin = types.ModuleType("kaolin")
        kaolin.utils = types.ModuleType("kaolin.utils")
        kaolin.utils.testing = types.ModuleType("kaolin.utils.testing")
        kaolin.utils.testing.check_tensor = lambda *a, **k: True
        sys.modules.update({"kaolin": kaolin, "kaolin.utils": kaolin.utils, "kaolin.utils.testing": kaolin.utils.testing})
        sys.path.insert(0, str(TRELLIS_DIR))

        import torch
        from trellis.pipelines import TrellisImageTo3DPipeline

        self.torch = torch
        self.pipe = TrellisImageTo3DPipeline.from_pretrained(TRELLIS_REPO)
        self.pipe.cuda()

    def __call__(self, image, seed, target_faces):
        with self.torch.inference_mode():
            # preprocess_image (run inside) removes the background with rembg and crops to the object.
            mesh = self.pipe.run(image, seed=seed, formats=["mesh"])["mesh"][0]
        vertices = mesh.vertices.float().cpu().numpy() @ Z_UP_TO_Y_UP
        faces = mesh.faces.cpu().numpy()
        colors = None
        if mesh.vertex_attrs is not None and mesh.vertex_attrs.shape[-1] >= 3:
            colors = (mesh.vertex_attrs[:, :3].clamp(0, 1).float().cpu().numpy() * 255).round().astype(np.uint8)
        raw_faces = len(faces)
        vertices, faces, colors = decimate(vertices, faces, colors, target_faces)
        self.torch.cuda.empty_cache()
        return to_glb(vertices, faces, colors), {"faces": len(faces), "raw_faces": raw_faces}
