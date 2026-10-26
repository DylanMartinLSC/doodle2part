"""Live 2D preview: one-step SD-Turbo img2img, adapted from SketchLive.

The preview doubles as TRELLIS's reference image, so prompts get a suffix that
asks for a single centred object on a plain background.
"""

import time

from PIL import Image, ImageFilter, ImageOps

SIZE = 512
REPO = "stabilityai/sd-turbo"
OBJECT_HINT = "single object, centered, full view, plain white background, 3d render, soft studio lighting"


class MockPreview:
    """Stand-in that stylizes the sketch so the UI works without a GPU."""

    def __call__(self, image, prompt, strength, seed):
        time.sleep(0.05)
        img = image.filter(ImageFilter.GaussianBlur(6 * strength))
        return ImageOps.posterize(ImageOps.autocontrast(img), 3)


class TurboPreview:
    def __init__(self, device="cuda"):
        import torch
        from diffusers import AutoencoderTiny, AutoPipelineForImage2Image
        from diffusers.utils import logging

        logging.set_verbosity_error()  # custom timesteps trigger a scheduler warning on every frame
        self.torch = torch
        self.device = device
        pipe = AutoPipelineForImage2Image.from_pretrained(REPO, variant="fp16", torch_dtype=torch.float16)
        # TAESD is much faster at encode/decode for a small cost in fine detail.
        pipe.vae = AutoencoderTiny.from_pretrained("madebyollin/taesd", torch_dtype=torch.float16)
        pipe.to(device)
        pipe.unet.to(memory_format=torch.channels_last)
        pipe.set_progress_bar_config(disable=True)
        self.pipe = pipe
        self.cached_prompt = (None, None)  # (prompt, embeddings)
        self(Image.new("RGB", (SIZE, SIZE), "white"), "warmup", 0.5, 0)  # so the first stroke isn't slow

    def embed(self, prompt):
        """Text embeddings for the prompt, reused while it stays the same."""
        if self.cached_prompt[0] != prompt:
            self.cached_prompt = (prompt, self.pipe.encode_prompt(prompt, self.device, 1, False)[0])
        return self.cached_prompt[1]

    def __call__(self, image, prompt, strength, seed):
        torch = self.torch
        # diffusers rounds `strength` to whole scheduler steps, which for a 1-step model collapses the
        # slider onto t=499; an explicit timestep tracks the slider continuously.
        t = min(999, max(1, round(1000 * strength) - 1))
        pixels = torch.frombuffer(bytearray(image.tobytes()), dtype=torch.uint8).view(SIZE, SIZE, 3)
        pixels = pixels.to(self.device).permute(2, 0, 1)[None].float() / 255
        with torch.inference_mode():
            out = self.pipe(
                prompt_embeds=self.embed(prompt),
                image=pixels,
                strength=1.0,
                timesteps=[t],
                guidance_scale=0.0,
                generator=torch.Generator(self.device).manual_seed(seed),
                output_type="pt",
            ).images[0]
        return Image.fromarray((out.float() * 255).round().byte().permute(1, 2, 0).cpu().numpy())
