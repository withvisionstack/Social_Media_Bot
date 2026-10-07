import io
import logging
from pathlib import Path

from PIL import Image

from .nvidia import NvidiaProvider
# from .outro import OutroProvider


log = logging.getLogger(__name__)


PROVIDERS = [
    NvidiaProvider,
    # OutroProvider,
]


ESTILOS = {
    "abstrato": (
        "abstract dark background, deep navy blue and slate gray tones, "
        "subtle geometric shapes, soft glow, minimalist, cinematic lighting, "
        "no text, no letters, no watermark, empty space in the center"
    ),
    "foto": (
        "realistic photograph, natural lighting, shallow depth of field, "
        "moody navy and teal color grading, clean composition, "
        "no text, no signs, no logos, no watermark"
    ),
}


def _cobrir(img: Image.Image, w: int, h: int) -> Image.Image:
    """
    Redimensiona a imagem mantendo a proporção e corta o excesso
    para preencher exatamente w x h.
    """
    if img.width <= 0 or img.height <= 0:
        raise ValueError(
            "A imagem recebida possui dimensões inválidas."
        )

    if w <= 0 or h <= 0:
        raise ValueError(
            "A largura e a altura devem ser maiores que zero."
        )

    escala = max(
        w / img.width,
        h / img.height,
    )

    novo_tamanho = (
        round(img.width * escala),
        round(img.height * escala),
    )

    img = img.resize(
        novo_tamanho,
        Image.Resampling.LANCZOS,
    )

    x = (img.width - w) // 2
    y = (img.height - h) // 2

    return img.crop(
        (x, y, x + w, y + h)
    )


async def _gerar(
    prompt: str,
    saida: str,
    w: int,
    h: int,
) -> str:
    """
    Tenta gerar uma imagem usando os provedores configurados.

    Se um provedor falhar, tenta o próximo. Caso todos falhem,
    lança uma exceção contendo os erros encontrados.
    """
    if not prompt or not prompt.strip():
        raise ValueError("O prompt não pode estar vazio.")

    if not saida or not saida.strip():
        raise ValueError("O caminho de saída não pode estar vazio.")

    if w <= 0 or h <= 0:
        raise ValueError(
            "A largura e a altura devem ser maiores que zero."
        )

    if not PROVIDERS:
        raise RuntimeError(
            "Nenhum provedor de geração de imagens foi configurado."
        )

    erros = []

    caminho_saida = Path(saida)

    # Cria o diretório de saída, se necessário.
    caminho_saida.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    for provider_cls in PROVIDERS:
        try:
            provider = provider_cls()

            dados = await provider.generate_image(prompt)

            if not dados:
                raise ValueError(
                    "O provedor retornou dados de imagem vazios."
                )

            img = Image.open(
                io.BytesIO(dados)
            ).convert("RGB")

            img = _cobrir(img, w, h)

            img.save(
                caminho_saida,
                format="PNG",
            )

            log.info(
                "Imagem gerada com sucesso usando %s: %s",
                provider_cls.__name__,
                caminho_saida,
            )

            return str(caminho_saida)

        except Exception as e:
            msg = (
                f"{provider_cls.__name__}: "
                f"{type(e).__name__}: {e}"
            )

            log.warning(
                "Falha no provedor %s: %s",
                provider_cls.__name__,
                e,
                exc_info=True,
            )

            erros.append(msg)

    detalhes = "\n".join(
        f"- {erro}"
        for erro in erros
    )

    raise RuntimeError(
        "Não foi possível gerar a imagem com nenhum provedor.\n"
        f"{detalhes}"
    )


async def gerar_fundo(
    cena: str,
    saida: str,
    w: int = 1080,
    h: int = 1350,
) -> str:
    """
    Gera um fundo abstrato para a cena informada.
    """
    if not cena or not cena.strip():
        raise ValueError(
            "A cena não pode estar vazia."
        )

    prompt = (
        f"{ESTILOS['abstrato']}, "
        f"subject: {cena.strip()}"
    )

    return await _gerar(
        prompt=prompt,
        saida=saida,
        w=w,
        h=h,
    )


async def gerar_foto(
    descricao: str,
    saida: str,
    w: int = 900,
    h: int = 560,
) -> str:
    """
    Gera uma foto realista baseada na descrição.
    """
    if not descricao or not descricao.strip():
        raise ValueError(
            "A descrição não pode estar vazia."
        )

    prompt = (
        f"{ESTILOS['foto']}, "
        f"{descricao.strip()}"
    )

    return await _gerar(
        prompt=prompt,
        saida=saida,
        w=w,
        h=h,
    )
