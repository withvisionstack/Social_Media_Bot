import os
import shutil
import asyncio
import logging
from pathlib import Path
from functools import wraps
from telegram.request import HTTPXRequest
from telegram.ext import MessageHandler, filters

from dotenv import load_dotenv
from telegram import (Update, InlineKeyboardButton as B, InlineKeyboardMarkup as M,
                      InputMediaPhoto)
from telegram.error import BadRequest
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

from core.pipeline import criar_conteudo
from core.texto import gerar_ideias, TextoIndisponivel


load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("bot")

PERMITIDO = int(os.getenv("TELEGRAM_ALLOWED_ID", "0"))
PADRAO = {"tema": "", "objetivo": "conteudo", "formato": "carrossel", "slides": 4,
          "foto_capa": True, "img_slides": False, "encerramento": True}
LOCK = asyncio.Lock()   # uma geração por vez (protege as cotas e o Chromium)


def so_dono(fn):
    @wraps(fn)
    async def interno(update: Update, context: ContextTypes.DEFAULT_TYPE):
        u = update.effective_user
        if not u or u.id != PERMITIDO:
            return
        return await fn(update, context)
    return interno


# ---------- menu de opções ----------
def total_imagens(c: dict) -> int:
    base = 1 if c["formato"] == "post" else 1 + c["slides"]
    return base + (1 if c["encerramento"] else 0)


def texto_menu(c: dict) -> str:
    return (f"📌 Tema: {c['tema']}\n\n"
            f"Ajuste as opções e toque em Gerar.\n"
            f"🖼 Total de imagens: {total_imagens(c)}")


def teclado(c: dict) -> M:
    def sel(ativo, nome): return ("🔘 " if ativo else "⚪ ") + nome
    def chk(ativo, nome): return ("✅ " if ativo else "⬜ ") + nome

    linhas = [
        [B(sel(c["objetivo"] == "conteudo", "Conteúdo"), callback_data="c:obj:conteudo"),
         B(sel(c["objetivo"] == "venda", "Venda"), callback_data="c:obj:venda")],
        [B(sel(c["formato"] == "post", "Post único"), callback_data="c:fmt:post"),
         B(sel(c["formato"] == "carrossel", "Carrossel"), callback_data="c:fmt:carrossel")],
    ]
    if c["formato"] == "carrossel":
        linhas.append([B(("●" if c["slides"] == n else "") + str(n), callback_data=f"c:sl:{n}")
                       for n in (2, 3, 4, 5, 6, 8)])
    linhas.append([B(chk(c["foto_capa"], "Foto na capa"), callback_data="c:t:foto_capa")])
    if c["formato"] == "carrossel":
        linhas.append([B(chk(c["img_slides"], "Foto nos slides"), callback_data="c:t:img_slides")])
    linhas.append([B(chk(c["encerramento"], "Slide de encerramento"), callback_data="c:t:encerramento")])
    linhas.append([B("🚀 Gerar", callback_data="go"), B("❌ Cancelar", callback_data="x")])
    return M(linhas)


async def editar(q, texto: str, markup=None):
    try:
        await q.edit_message_text(texto, reply_markup=markup)
    except BadRequest as e:
        if "not modified" not in str(e).lower():
            raise


async def abrir_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, tema: str, **forcar):
    c = {**context.user_data.get("cfg", PADRAO), "tema": tema, **forcar}
    context.user_data["cfg"] = c
    await update.effective_chat.send_message(texto_menu(c), reply_markup=teclado(c))


# ---------- comandos ----------
@so_dono
async def ajuda(update, context):
    await update.message.reply_text(
        "Comandos:\n"
        "/ideias [foco] — sugere ideias de posts (venda ou conteúdo)\n"
        "/carrossel <tema> — cria um carrossel\n"
        "/post <tema> — cria um post único\n\n"
        "Depois de escolher o tema, você ajusta formato, slides e imagens nos botões.")


@so_dono
async def cmd_ideias(update, context):
    context.user_data["foco"] = " ".join(context.args)
    context.user_data["ideias_vistas"] = []
    await update.message.reply_text(
        "Que tipo de ideia você quer?",
        reply_markup=M([[B("💰 Venda", callback_data="tipo:venda"),
                         B("📚 Conteúdo", callback_data="tipo:conteudo")],
                        [B("🎲 Misto", callback_data="tipo:misto")]]))


@so_dono
async def cmd_carrossel(update, context):
    tema = " ".join(context.args).strip()
    if not tema:
        await update.message.reply_text("Use: /carrossel seu tema aqui")
        return
    await abrir_menu(update, context, tema, formato="carrossel")


@so_dono
async def cmd_post(update, context):
    tema = " ".join(context.args).strip()
    if not tema:
        await update.message.reply_text("Use: /post seu tema aqui")
        return
    await abrir_menu(update, context, tema, formato="post")


# ---------- ideias ----------
async def mostrar_ideias(q, context, tipo: str):
    foco = context.user_data.get("foco", "")
    vistas = context.user_data.get("ideias_vistas", [])
    await editar(q, "💡 Pensando em ideias…")
    try:
        ideias = await gerar_ideias(foco, tipo, 6, vistas)
    except TextoIndisponivel:
        await editar(q, "Limite atingido nos provedores de texto. Tente de novo em alguns minutos.")
        return
    context.user_data["ideias"] = ideias
    context.user_data["ideias_vistas"] = (vistas + [i["titulo"] for i in ideias])[-30:]

    icone = {"venda": "💰", "conteudo": "📚"}
    corpo = "\n\n".join(
        f"{n}. {icone[i['tipo']]} {i['titulo']}\n    {i.get('gancho', '')}"
        for n, i in enumerate(ideias, 1))
    await editar(q, corpo[:3900], M([
        [B(str(n), callback_data=f"id:{n - 1}") for n in range(1, len(ideias) + 1)],
        [B("🔄 Outras ideias", callback_data=f"tipo:{tipo}"), B("❌ Cancelar", callback_data="x")],
    ]))


# ---------- geração ----------
async def executar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    c = context.user_data["cfg"]
    chat = update.effective_chat
    if LOCK.locked():
        await chat.send_message("Ainda estou gerando outro post. Aguarde terminar.")
        return

    async with LOCK:
        aviso = await chat.send_message("⏳ Gerando… leva de 1 a 3 minutos.")
        try:
            r = await criar_conteudo(
                c["tema"], formato=c["formato"], n_slides=c["slides"],
                foto_capa=c["foto_capa"], img_slides=c["img_slides"],
                encerramento=c["encerramento"], objetivo=c["objetivo"])
        except TextoIndisponivel:
            await aviso.edit_text("Limite atingido nos provedores de texto. Tente em alguns minutos.")
            return
        except Exception as e:
            log.exception("erro ao gerar")
            await aviso.edit_text(f"Erro ao gerar: {type(e).__name__}: {e}"[:400])
            return
        await aviso.delete()

        abertos = []
        try:
            for p in r["imagens"]:
                abertos.append(open(p, "rb"))
            if len(abertos) == 1:
                await chat.send_photo(abertos[0], write_timeout=90, read_timeout=90)
            else:
                await chat.send_media_group([InputMediaPhoto(f) for f in abertos],
                                            write_timeout=120, read_timeout=120)
        finally:
            for f in abertos:
                f.close()

        context.user_data["ultimo"] = r
        await chat.send_message(
            f"📝 Legenda sugerida:\n\n{r['legenda']}"[:4000],
            reply_markup=M([[B("✅ Aprovar", callback_data="ok"), B("🔄 Refazer", callback_data="redo")],
                            [B("❌ Descartar", callback_data="x")]]))


# ---------- botões ----------
@so_dono
async def botoes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    d = q.data
    c = context.user_data.get("cfg")

    if d.startswith("tipo:"):
        await mostrar_ideias(q, context, d.split(":")[1])

    elif d.startswith("id:"):
        ideias = context.user_data.get("ideias", [])
        i = int(d.split(":")[1])
        if i >= len(ideias):
            return
        ideia = ideias[i]
        tema = ideia["titulo"] + (f" — {ideia['gancho']}" if ideia.get("gancho") else "")
        c = {**context.user_data.get("cfg", PADRAO), "tema": tema,
             "objetivo": ideia["tipo"], "formato": ideia["formato"]}
        context.user_data["cfg"] = c
        await editar(q, texto_menu(c), teclado(c))

    elif d.startswith("c:") and c:
        _, campo, valor = d.split(":")
        if campo == "obj":
            c["objetivo"] = valor
        elif campo == "fmt":
            c["formato"] = valor
        elif campo == "sl":
            c["slides"] = int(valor)
        elif campo == "t":
            c[valor] = not c[valor]
        await editar(q, texto_menu(c), teclado(c))

    elif d == "go" and c:
        await editar(q, f"🚀 Gerando: {c['tema']}")
        await executar(update, context)

    elif d == "redo" and c:
        await q.edit_message_reply_markup(None)
        await executar(update, context)

    elif d == "ok":
        r = context.user_data.get("ultimo")
        if not r:
            return
        destino = Path("saida/aprovados") / Path(r["pasta"]).name
        shutil.copytree(r["pasta"], destino, dirs_exist_ok=True)
        await q.edit_message_reply_markup(None)
        await update.effective_chat.send_message(f"✅ Aprovado e salvo em {destino}")

    elif d == "x":
        await editar(q, "Cancelado.")


def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token or not PERMITIDO:
        raise SystemExit("Configure TELEGRAM_BOT_TOKEN e TELEGRAM_ALLOWED_ID no .env")

    async def _debug(update, context):
        u = update.effective_user
        print(f"Mensagem de id={u.id} @{u.username} | permitido={PERMITIDO}")

    app = (
        Application.builder()
        .token(token)
        .request(HTTPXRequest(connect_timeout=30, read_timeout=30,
                              write_timeout=30, pool_timeout=30))
        .get_updates_request(HTTPXRequest(connect_timeout=30, read_timeout=60,
                                          write_timeout=30, pool_timeout=30))
        .build()
    )
    app.add_handler(CommandHandler(["start", "ajuda"], ajuda))
    app.add_handler(MessageHandler(filters.ALL, _debug), group=1)
    app.add_handler(CommandHandler("ideias", cmd_ideias))
    app.add_handler(CommandHandler("carrossel", cmd_carrossel))
    app.add_handler(CommandHandler("post", cmd_post))
    app.add_handler(CallbackQueryHandler(botoes))
    log.info("Bot no ar.")
    app.run_polling(bootstrap_retries=5)


if __name__ == "__main__":
    main()