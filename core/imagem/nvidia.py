import os
import asyncio
import base64

import httpx
from dotenv import load_dotenv

from .base import ImageProvider

load_dotenv()

# garante uma geração por vez, mesmo se o código chamar em paralelo
_fila = asyncio.Semaphore(1)


class NvidiaProvider(ImageProvider):
    name = "nvidia"

    def __init__(self):
        self.api_key = os.getenv("NVIDIA_API_KEY")
        if not self.api_key:
            raise ValueError("NVIDIA_API_KEY não configurada.")
        self.url = "https://ai.api.nvidia.com/v1/genai/black-forest-labs/flux.2-klein-4b"

    async def generate_image(self, prompt: str, width: int = 1024, height: int = 1024) -> bytes:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        payload = {"prompt": prompt, "height": height, "width": width,
                   "cfg_scale": 1, "samples": 1, "seed": 0, "steps": 4}
        timeout = httpx.Timeout(connect=10.0, read=90.0, write=30.0, pool=10.0)
        tentativas = 3

        async with _fila:
            for n in range(1, tentativas + 1):
                try:
                    async with httpx.AsyncClient(timeout=timeout) as client:
                        r = await client.post(self.url, headers=headers, json=payload)
                except httpx.TimeoutException as e:
                    if n == tentativas:
                        raise RuntimeError(f"NVIDIA: timeout após {tentativas} tentativas") from e
                    await asyncio.sleep(5 * n)
                    continue

                if r.status_code in (429, 500, 502, 503, 504) and n < tentativas:
                    await asyncio.sleep(8 * n)
                    continue
                if r.status_code != 200:
                    raise RuntimeError(f"NVIDIA retornou {r.status_code}: {r.text[:300]}")
                return base64.b64decode(r.json()["artifacts"][0]["base64"])