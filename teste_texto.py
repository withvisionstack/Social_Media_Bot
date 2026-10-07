import asyncio, time
from core.texto import gerar_texto

async def main():
    for tema in ["produtividade", "saúde mental", "tecnologia","sistemas"]:
        t = time.time()
        post = await gerar_texto(tema)
        print(f"\n[{tema}] {time.time() - t:.1f}s")
        print(post)

asyncio.run(main())