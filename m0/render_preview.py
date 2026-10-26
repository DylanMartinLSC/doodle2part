"""Render a .glb (vertex colours) to a PNG for quick visual checks.  python render_preview.py in.glb out.png"""
import sys

import numpy as np
import pyvista as pv
import trimesh

mesh = trimesh.load(sys.argv[1], force="mesh")
faces = np.hstack([np.full((len(mesh.faces), 1), 3), mesh.faces]).ravel()
pd = pv.PolyData(np.asarray(mesh.vertices), faces)
pl = pv.Plotter(off_screen=True, window_size=(768, 768))
colors = getattr(mesh.visual, "vertex_colors", None)
if colors is not None and len(colors) == len(mesh.vertices):
    pd["rgb"] = np.asarray(colors)[:, :3]
    pl.add_mesh(pd, scalars="rgb", rgb=True)
else:
    pl.add_mesh(pd, color="lightsteelblue", smooth_shading=True)
pl.camera_position = "iso"
pl.screenshot(sys.argv[2])
