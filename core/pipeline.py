import time
from pathlib import Path

from config import PERFIL
from core.texto import gerar_texto, gerar_carrossel
from core.imagem import gerar_fundo, gerar_foto
from core.render import renderizar


async def criar_encerramento(fundo: str | None = None,
                             saida: str = "saida/encerramento.png",
                             gerar: bool = True) -> dict:
    """Slide final de CTA (link na bio). Os textos vêm do config.py."""
    if fundo is None and gerar:
        fundo = await gerar_fundo("dark technology network, subtle glow", "saida/fundo_cta.png")
    png = await renderizar(PERFIL["encerramento"], fundo, saida,
                           template="encerramento", foto=None, marca=PERFIL["marca"])
    return {"imagem": png}


async def criar_conteudo(tema: str, formato: str = "carrossel", n_slides: int = 4,
                         foto_capa: bool = True, img_slides: bool = False,
                         encerramento: bool = True, objetivo: str = "conteudo") -> dict:
    marca = PERFIL["marca"]
    carrossel = formato == "carrossel"
    pasta = Path("saida") / f"{formato}_{time.strftime('%Y%m%d_%H%M%S')}"
    pasta.mkdir(parents=True, exist_ok=True)

    if carrossel:
        texto = await gerar_carrossel(tema, n_slides, objetivo, img_slides)
    else:
        texto = await gerar_texto(tema, objetivo)

    # o fundo nunca falha (tem reserva local); a foto pode vir vazia
    fundo = await gerar_fundo(texto.get("cena", tema), str(pasta / "_fundo.png"))
    foto = None
    if foto_capa:
        foto = await gerar_foto(texto.get("foto", tema), str(pasta / "_foto.png"))

    capa = await renderizar(
        {"titulo": texto["titulo"], "subtitulo": texto["subtitulo"]},
        fundo, str(pasta / "01_capa.png"),
        template="capa_foto" if foto else "capa", foto=foto, marca=marca,
        extras={"total": n_slides} if carrossel else {})
    imagens = [capa]

    if carrossel:
        for i, slide in enumerate(texto["slides"], start=1):
            foto_s = None
            if img_slides:
                foto_s = await gerar_foto(slide.get("foto") or slide["titulo"],
                                          str(pasta / f"_foto_{i}.png"), w=900, h=480)
            imagens.append(await renderizar(
                slide, fundo, str(pasta / f"{i + 1:02d}_slide.png"),
                template="slide_foto" if foto_s else "slide", foto=foto_s, marca=marca,
                extras={"numero": i, "total": n_slides}))

    if encerramento:
        fim = await criar_encerramento(
            fundo, str(pasta / f"{len(imagens) + 1:02d}_encerramento.png"), gerar=False)
        imagens.append(fim["imagem"])

    legenda = texto["legenda"] + "\n\n" + " ".join(texto["hashtags"])
    (pasta / "legenda.txt").write_text(legenda, encoding="utf-8")
    return {"pasta": str(pasta), "imagens": imagens, "legenda": legenda}