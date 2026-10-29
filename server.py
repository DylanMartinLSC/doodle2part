"""Doodle2Part server: sketch -> live 2D preview -> 3D mesh.

The browser streams canvas frames over a WebSocket and gets SD-Turbo previews
back (newest frame wins, as in SketchLive). "Make 3D" posts the current
preview, which TRELLIS turns into a vertex-coloured GLB.

    python server.py           # real models (CUDA GPU)
    python server.py --mock    # no models, for UI development
"""

import argparse
import asyncio
import base64
import io
import os
import time
from pathlib import Path

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image

from preview import OBJECT_HINT, SIZE

ROOT = Path(__file__).parent
STATIC = ROOT / "static"
OUTPUTS = Path(os.environ.get("DOODLE2PART_OUTPUTS", ROOT / "outputs"))


def decode_image(data_url):
    raw = base64.b64decode(data_url.split(",", 1)[1])
    img = Image.open(io.BytesIO(raw)).convert("RGBA")
    # Composite onto white so transparent canvas areas aren't black.
    bg = Image.new("RGBA", img.size, "white")
    return Image.alpha_composite(bg, img).convert("RGB").resize((SIZE, SIZE))


def encode_image(img, quality=85):
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def create_app(preview, mesher, target_faces):
    app = FastAPI()
    # Both models share one GPU; a 3D job briefly pauses the live preview.
    gpu_lock = asyncio.Lock()
    OUTPUTS.mkdir(exist_ok=True)

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html")

    @app.post("/make3d")
    async def make3d(body: dict):
        started = time.perf_counter()
        try:
            image = decode_image(body["image"])
            seed = int(body.get("seed", 0))
            async with gpu_lock:
                glb, stats = await asyncio.to_thread(mesher, image, seed, target_faces)
        except Exception as e:
            return JSONResponse({"error": f"{type(e).__name__}: {e}"}, status_code=500)
        name = time.strftime("%Y%m%d-%H%M%S")
        (OUTPUTS / f"{name}.glb").write_bytes(glb)
        image.save(OUTPUTS / f"{name}.jpg", quality=90)
        return {"glb": f"/outputs/{name}.glb", "thumb": f"/outputs/{name}.jpg",
                "ms": round((time.perf_counter() - started) * 1000), **stats}

    @app.websocket("/ws")
    async def ws(socket: WebSocket):
        await socket.accept()
        latest = None  # newest unprocessed frame; stays None once the client disconnects
        frame_ready = asyncio.Event()

        async def receive():
            # Keep only the newest frame; older ones are stale by the time the GPU frees up.
            nonlocal latest
            try:
                while True:
                    latest = await socket.receive_json()
                    frame_ready.set()
            except WebSocketDisconnect:
                latest = None
                frame_ready.set()

        receiver = asyncio.create_task(receive())
        try:
            while True:
                await frame_ready.wait()
                frame_ready.clear()
                msg, latest = latest, None
                if msg is None:
                    break
                started = time.perf_counter()
                prompt = ", ".join(filter(None, [msg.get("prompt", "").strip(), OBJECT_HINT]))
                try:
                    args = (decode_image(msg["image"]), prompt, float(msg.get("strength", 0.75)), int(msg.get("seed", 0)))
                    async with gpu_lock:
                        result = await asyncio.to_thread(preview, *args)
                except Exception as e:
                    await socket.send_json({"id": msg.get("id"), "error": f"{type(e).__name__}: {e}"})
                    continue
                await socket.send_json({
                    "id": msg.get("id"),
                    "image": encode_image(result),
                    "ms": round((time.perf_counter() - started) * 1000),
                })
        except (WebSocketDisconnect, RuntimeError):
            pass  # client went away mid-send
        finally:
            receiver.cancel()

    app.mount("/outputs", StaticFiles(directory=OUTPUTS), name="outputs")
    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mock", action="store_true", help="run without models")
    parser.add_argument("--faces", type=int, default=100_000, help="decimate meshes to about this many faces")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7861)
    args = parser.parse_args()

    if args.mock:
        from mesh import MockMesh
        from preview import MockPreview

        preview, mesher = MockPreview(), MockMesh()
    else:
        from mesh import TrellisMesh
        from preview import TurboPreview

        # TRELLIS first: it's the bigger download, so a missing-weights error shows up early.
        mesher = TrellisMesh()
        preview = TurboPreview()
    uvicorn.run(create_app(preview, mesher, args.faces), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
