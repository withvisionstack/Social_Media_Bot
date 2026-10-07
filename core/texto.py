import os, re, json, time, random, logging
from pathlib import Path
from openai import AsyncOpenAI, RateLimitError
from dotenv import load_dotenv
from config import PERFIL

load_dotenv()
log = logging.getLogger(__name__)

HISTORICO = Path(__file__).resolve().parent.parent / "saida" / "historico.json"
PAUSA_429 = 600

PROVEDORES = [
    {"nome": "nemotron", "url": "https://integrate.api.nvidia.com/v1",
     "chave": "NVIDIA_NEMOTRON_API_KEY", "modelo": "LLM_NVIDIA_MODEL",
     "max_tokens": 3000, "extra": {}},
    {"nome": "gemma", "url": "https://openrouter.ai/api/v1",
     "chave": "OPENROUTER_API_KEY", "modelo": "LLM_OPENROUTER_MODEL",
     "max_tokens": 1200, "extra": {}},
    {"nome": "gemini", "url": "https://generativelanguage.googleapis.com/v1beta/openai/",
     "chave": "GEMINI_API_KEY", "modelo": "LLM_GEMINI_MODEL",
     "max_tokens": 1200, "extra": {}},
    {"nome": "openrouter2", "url": "https://openrouter.ai/api/v1",
     "chave": "OPENROUTER_API_KEY", "modelo": "LLM_OPENROUTER_MODEL_2",
     "max_tokens": 1200, "extra": {}},
]

INSTRUCOES = (
    "Você escreve posts de Instagram em português do Brasil. "
    "Nos títulos, use maiúscula só na primeira letra e em nomes próprios, "
    "como se escreve em português (nada de Title Case). "
    "Responda SOMENTE com um JSON válido, sem markdown e sem explicações."
)

TOM = {
    "venda": ("Objetivo: VENDER serviços. Estrutura: problema do cliente, consequência de "
              "não resolver, solução, chamada para entrar em contato. Seja específico e "
              "persuasivo, sem exagero."),
    "conteudo": ("Objetivo: educar e gerar autoridade. Dicas práticas e específicas, "
                 "sem enrolação e sem frases genéricas."),
}



LIMITES = {"titulo": 8, "subtitulo": 15}
OBRIGATORIOS = ("titulo", "subtitulo", "legenda", "hashtags")

_bloqueado_ate: dict[str, float] = {}


class TextoIndisponivel(RuntimeError):
    """Todos os provedores falharam ou estão em pausa."""

def _perfil() -> str:
        p = PERFIL
        return (f"Perfil: {p['nicho']}. Público: {p['publico']}. "
                f"Serviços: {', '.join(p['servicos'])}. "
                "Não invente números, clientes, prazos nem resultados.")


def _limpar(texto: str) -> dict:
    texto = re.sub(r"<think>.*?</think>", "", texto, flags=re.S)
    ini, fim = texto.find("{"), texto.rfind("}")
    return json.loads(texto[ini:fim + 1])


def _valido(d: dict) -> bool:
    if not all(k in d for k in OBRIGATORIOS):
        return False
    return all(len(str(d[k]).split()) <= m for k, m in LIMITES.items())


def _eh_limite(e: Exception) -> bool:
    return isinstance(e, RateLimitError) or "429" in str(e)


def _salvar_historico(tema: str, dados: dict) -> None:
    try:
        HISTORICO.parent.mkdir(exist_ok=True)
        itens = json.loads(HISTORICO.read_text(encoding="utf-8")) if HISTORICO.exists() else []
        itens.append({"tema": tema, "quando": time.strftime("%Y-%m-%d %H:%M"), "post": dados})
        HISTORICO.write_text(json.dumps(itens[-200:], ensure_ascii=False, indent=2),
                             encoding="utf-8")
    except Exception as e:
        log.warning("não foi possível salvar o histórico: %s", e)


def texto_do_historico() -> dict | None:
    try:
        itens = json.loads(HISTORICO.read_text(encoding="utf-8"))
        return random.choice(itens)["post"] if itens else None
    except Exception:
        return None


async def _gerar_json(base: str, validar, tema: str, salvar: bool = True) -> dict:
    erros = []
    for p in PROVEDORES:
        chave, modelo = os.getenv(p["chave"]), os.getenv(p["modelo"])
        if not chave or not modelo:
            continue
        if _bloqueado_ate.get(p["nome"], 0) > time.time():
            erros.append(f"{p['nome']}: em pausa por limite de uso")
            continue

        client = AsyncOpenAI(base_url=p["url"], api_key=chave, timeout=120)
        pedido = base
        for _ in range(2):
            try:
                r = await client.chat.completions.create(
                    model=modelo, temperature=0.7, max_tokens=max(p["max_tokens"], 2500),
                    messages=[{"role": "user", "content": pedido}],
                    extra_body=p["extra"] or None,
                )
                dados = _limpar(r.choices[0].message.content or "")
                if validar(dados):
                    log.info("texto gerado por %s", p["nome"])
                    if salvar:
                        _salvar_historico(tema, dados)
                    return dados
                pedido = base + "\nATENÇÃO: respeite todos os campos, a quantidade de slides e os limites de palavras."
            except Exception as e:
                if _eh_limite(e):
                    _bloqueado_ate[p["nome"]] = time.time() + PAUSA_429
                    log.warning("%s no limite, pausado por %ss", p["nome"], PAUSA_429)
                else:
                    log.warning("%s falhou: %s", p["nome"], e)
                erros.append(f"{p['nome']}: {type(e).__name__}: {e}")
                break

    raise TextoIndisponivel("Nenhum provedor de texto respondeu -> " + " | ".join(erros))

async def gerar_texto(tema: str, objetivo: str = "conteudo") -> dict:
    base = (
        f"{INSTRUCOES}\n\n{_perfil()}\n{TOM[objetivo]}\n\nTema: {tema}\n"
        'Formato: {"titulo": "máx 8 palavras", "subtitulo": "máx 15 palavras", '
        '"legenda": "2 a 4 frases", "hashtags": ["#a", "#b", "#c"], '
        '"cena": "descrição curta em inglês para um fundo abstrato", '
        '"foto": "descrição em inglês de uma cena concreta e fotografável ligada ao tema, '
        'sem pessoas em primeiro plano, sem texto"}'
    )
    return await _gerar_json(base, _valido, tema)


async def gerar_carrossel(tema: str, n_slides: int = 4, objetivo: str = "conteudo",
                          com_foto_slides: bool = False) -> dict:
    campo_foto = (', "foto": "cena fotografável em inglês, sem pessoas em primeiro plano, sem texto"'
                  if com_foto_slides else "")
    base = (
        f"{INSTRUCOES}\n\n{_perfil()}\n{TOM[objetivo]}\n\nTema: {tema}\n"
        f"Crie um carrossel com uma capa e exatamente {n_slides} slides de conteúdo. "
        "Cada slide traz UMA ideia, em sequência lógica (o primeiro prende, o último fecha). "
        'Formato: {"titulo": "capa, máx 8 palavras", "subtitulo": "capa, máx 15 palavras", '
        '"cena": "descrição curta em inglês para um fundo abstrato", '
        '"foto": "descrição em inglês de uma cena fotografável ligada ao tema, sem pessoas em primeiro plano, sem texto", '
        f'"slides": [{{"titulo": "máx 6 palavras", "texto": "máx 30 palavras"{campo_foto}}}], '
        '"legenda": "2 a 4 frases", "hashtags": ["#a", "#b", "#c"]}'
    )

    def validar(d: dict) -> bool:
        if not all(k in d for k in OBRIGATORIOS) or not isinstance(d.get("slides"), list):
            return False
        if len(d["slides"]) != n_slides:
            return False
        if not all(len(str(d[k]).split()) <= m for k, m in LIMITES.items()):
            return False
        return all(
            isinstance(s, dict) and s.get("titulo") and s.get("texto")
            and len(str(s["titulo"]).split()) <= 6 and len(str(s["texto"]).split()) <= 35
            for s in d["slides"]
        )

    return await _gerar_json(base, validar, tema)


async def gerar_ideias(foco: str = "", tipo: str = "misto", qtd: int = 6,
                       evitar: list[str] | None = None) -> list[dict]:
    pedido_tipo = {
        "venda": 'Todas com tipo "venda": posts que levem o público a contratar os serviços.',
        "conteudo": 'Todas com tipo "conteudo": posts que ensinem e gerem autoridade.',
        "misto": 'Misture tipos "venda" e "conteudo", cerca de metade de cada.',
    }[tipo]
    base = (
        f"{INSTRUCOES}\n\n{_perfil()}\n"
        f"Sugira {qtd} ideias de posts para Instagram. {pedido_tipo}\n"
        + (f"Foco ou assunto de interesse: {foco}\n" if foco else "")
        + (f"Não repita estas ideias: {'; '.join(evitar)}\n" if evitar else "")
        + 'Formato: {"ideias": [{"tipo": "venda ou conteudo", '
          '"titulo": "máx 12 palavras, claro e específico", '
          '"gancho": "uma frase com o ângulo do post", '
          '"formato": "carrossel ou post"}]}'
    )

    def validar(d: dict) -> bool:
        ideias = d.get("ideias")
        return (isinstance(ideias, list) and len(ideias) >= 3
                and all(isinstance(i, dict) and i.get("titulo") for i in ideias))

    d = await _gerar_json(base, validar, "ideias", salvar=False)
    ideias = d["ideias"][:qtd]
    padrao = "venda" if tipo == "venda" else "conteudo"
    for i in ideias:
        if i.get("tipo") not in ("venda", "conteudo"):
            i["tipo"] = padrao
        if i.get("formato") not in ("carrossel", "post"):
            i["formato"] = "carrossel"
    return ideias