import asyncio
from core.pipeline import criar_carrossel

r = asyncio.run(criar_carrossel("produtividade para freelancers", n_slides=4))
print(r["pasta"])
for img in r["imagens"]:
    print(img)