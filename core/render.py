from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from playwright.async_api import async_playwright


BASE = Path(__file__).resolve().parent.parent

env = Environment(
    loader=FileSystemLoader(BASE / "templates"),
    autoescape=True,
)

LOGO = BASE / "assets" / "logo.png"

# Campos que o LLM devolve somente para geração de imagens;
# o template não precisa deles.
CAMPOS_DE_IMAGEM = {"cena", "foto"}


def _uri(caminho: str | Path | None) -> str | None:
    """Converte um caminho existente em URI de arquivo."""
    if not caminho:
        return None

    caminho = Path(caminho)

    if not caminho.exists():
        return None

    return caminho.resolve().as_uri()


async def renderizar(
    dados: dict,
    fundo: str,
    saida: str,
    template: str = "capa_foto",
    foto: str | None = None,
    logo: str | None = str(LOGO),
    marca: str = "@seuperfil",
    w: int = 1080,
    h: int = 1350,
    extras: dict | None = None,
) -> str:
    """Renderiza o template HTML e salva o resultado como imagem."""

    # Remove do post os campos usados apenas para geração de imagens.
    post = {
        k: v
        for k, v in dados.items()
        if k not in CAMPOS_DE_IMAGEM
    }

    # Renderiza o template Jinja.
    html = env.get_template(f"{template}.html").render(
        post=post,
        imagens={
            "fundo": _uri(fundo),
            "foto": _uri(foto),
            "logo": _uri(logo),
        },
        marca=marca,
        w=w,
        h=h,
        **(extras or {}),
    )

    # Cria o diretório de saída temporário.
    tmp = BASE / "saida" / "_tmp.html"
    tmp.parent.mkdir(parents=True, exist_ok=True)

    tmp.write_text(html, encoding="utf-8")

    # Abre o HTML com Playwright e tira o screenshot.
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()

        try:
            page = await browser.new_page(
                viewport={
                    "width": w,
                    "height": h,
                }
            )

            await page.goto(
                tmp.resolve().as_uri(),
                wait_until="networkidle",
            )

            # Aguarda o carregamento das fontes.
            await page.evaluate("document.fonts.ready")

            await page.screenshot(path=saida)

        finally:
            await browser.close()

    return saida
