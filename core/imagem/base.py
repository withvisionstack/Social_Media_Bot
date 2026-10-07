class ImageProvider:
    name = "base"

    async def generate_image(self, prompt: str, width: int = 1024, height: int = 1024) -> bytes:
        raise NotImplementedError