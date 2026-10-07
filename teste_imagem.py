import asyncio, time
from core.imagem import gerar_fundo

t = time.time()
print(asyncio.run(gerar_fundo("technology", "saida/teste_fundo.png")))
print(f"{time.time() - t:.1f}s")