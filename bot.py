"""
Clara Bot — Assistente Estratégica Pessoal do Zambom
Stack: python-telegram-bot 21.5 | anthropic | groq
"""

import os
import base64
import logging
import tempfile
from pathlib import Path

from telegram import Update, BotCommand
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from telegram.constants import ParseMode, ChatAction

import anthropic
from groq import Groq

import PyPDF2
import pandas as pd


# ── Logging ───────────────────────────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ── Clients ───────────────────────────────────────────────────────────────────────────────────────
anthropic_client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
groq_client = Groq(api_key=os.environ["GROQ_API_KEY"])


# ── System Prompt ─────────────────────────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """
Você é Clara, assistente estratégica pessoal do Zambom.

## CONTEXTO
- **Empresa:** TRILIA — consultoria de crescimento comercial para empresas B2B
- **PSC (Processo de Sucesso do Cliente):** metodologia proprietária de onboarding, implantação e expansão
- **Zambom:** fundador e estrategista principal da TRILIA

## METODOLOGIA FSS — 5 Pilares
O diagnóstico FSS avalia os 5 pilares do sucesso comercial:
1. **Funil** — geração e qualificação de demanda
2. **Seleção** — critérios de ICP e segmentação
3. **Script** — abordagem, objeções e fechamento
4. **Squad** — time, treinamento e gestão
5. **Sistemas** — CRM, automações e dados

**KPIs do FSS:** taxa de conversão por etapa, CAC, LTV, churn, ciclo de venda, ARR/MRR

**Estrutura de fechamento:** diagnóstico → proposta de valor → prova social → oferta → urgência/escassez → CTA

## FRAMEWORK HORMOZI
- **$100M Offers:** Criar ofertas irresistíveis com alto valor percebido e baixo risco para o cliente
- **$100M Leads:** Estratégias de geração de demanda com mecanismos de atração e conversão

## COMO AGIR
- Seja direta, estratégica e orientada a resultado
- Use linguagem clara, sem rodeios
- Ofereça frameworks e estruturas práticas
- Quando analisar, use os pilares FSS como referência
- Responda sempre em português do Brasil
"""


# ── Conversation History (in-memory) ────────────────────────────────────────────────────────────────────────────────────
conversation_history: dict[int, list] = {}
MAX_HISTORY = 20


def get_history(chat_id: int) -> list:
    return conversation_history.setdefault(chat_id, [])


def add_to_history(chat_id: int, role: str, content: str) -> None:
    history = get_history(chat_id)
    history.append({"role": role, "content": content})
    if len(history) > MAX_HISTORY:
        conversation_history[chat_id] = history[-MAX_HISTORY:]


def clear_history(chat_id: int) -> None:
    conversation_history.pop(chat_id, None)


# ── Claude Helper ───────────────────────────────────────────────────────────────────────────────────────
def ask_claude(chat_id: int, user_message: str, extra_system: str = "") -> str:
    add_to_history(chat_id, "user", user_message)
    system = SYSTEM_PROMPT + ("\n\n" + extra_system if extra_system else "")
    response = anthropic_client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        system=system,
        messages=get_history(chat_id),
    )
    reply = response.content[0].text
    add_to_history(chat_id, "assistant", reply)
    return reply


# COMMAND HANDLERS

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "\ud83d\udc4b Olá! Sou a *Clara*, sua assistente estratégica.\n\n"
        "Posso te ajudar com:\n"
        "\u2022 \ud83d\udd0d `/diagnostico` \u2014 Diagnóstico FSS do cliente\n"
        "\u2022 \ud83d\udcde `/sdr` \u2014 Coach de SDR com scripts prontos\n"
        "\u2022 \ud83d\udcc4 `/proposta` \u2014 Gerador de proposta comercial\n"
        "\u2022 \ud83c\udfaf `/analisarcall` \u2014 Análise de call de vendas\n"
        "\u2022 \ud83d\uddd1\ufe0f `/limpar` \u2014 Limpar histórico da conversa\n\n"
        "Ou simplesmente me mande uma mensagem de texto, áudio, foto, PDF, Excel ou CSV!",
        parse_mode=ParseMode.MARKDOWN,
    )


async def limpar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    clear_history(update.effective_chat.id)
    await update.message.reply_text("\ud83d\uddd1\ufe0f Histórico limpo! Começando do zero.")


async def diagnostico_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    extra = (
        "O usuário quer fazer um diagnóstico FSS. Conduza uma entrevista estruturada "
        "perguntando sobre os 5 pilares (Funil, Seleção, Script, Squad, Sistemas). "
        "Faça uma pergunta por vez. Colete as respostas e ao final gere um diagnóstico "
        "completo com pontuação de 0-10 por pilar, análise de gaps e top 3 recomendações "
        "prioritárias baseadas no framework FSS e Hormozi."
    )
    await update.message.reply_chat_action(ChatAction.TYPING)
    reply = ask_claude(chat_id, "[COMANDO: /diagnostico] Iniciar diagnóstico FSS", extra)
    await update.message.reply_text(reply, parse_mode=ParseMode.MARKDOWN)


async def sdr_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    extra = (
        "O usuário quer treinar como SDR. Aja como coach de vendas especialista. "
        "Ofereça um menu com: (1) Script de cold call, (2) Script de cold email, "
        "(3) Tratamento de objeções comuns (sem tempo / sem verba / já temos fornecedor), "
        "(4) Técnica de follow-up eficaz. Pergunte qual deles quer explorar primeiro."
    )
    await update.message.reply_chat_action(ChatAction.TYPING)
    reply = ask_claude(chat_id, "[COMANDO: /sdr] Ativar coach SDR", extra)
    await update.message.reply_text(reply, parse_mode=ParseMode.MARKDOWN)


async def proposta_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    extra = (
        "O usuário quer gerar uma proposta comercial. Conduza uma coleta rápida de informações: "
        "nome do cliente, segmento/mercado, dores principais, objetivo com a solução, prazo, "
        "investimento estimado e diferenciais da solução. Depois gere uma proposta comercial "
        "completa no framework Hormozi: problema \u2192 solução \u2192 mecanismo único \u2192 prova social \u2192 "
        "oferta detalhada \u2192 garantia \u2192 CTA com urgência."
    )
    await update.message.reply_chat_action(ChatAction.TYPING)
    reply = ask_claude(chat_id, "[COMANDO: /proposta] Gerar proposta comercial", extra)
    await update.message.reply_text(reply, parse_mode=ParseMode.MARKDOWN)


async def analisarcall_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    extra = (
        "O usuário vai colar a transcrição ou resumo de uma call de vendas. "
        "Analise usando os 5 pilares FSS e o framework Hormozi. Avalie: "
        "(1) Rapport e abertura, (2) Descoberta de dores e qualificação, "
        "(3) Apresentação da solução e proposta de valor, "
        "(4) Objeções levantadas e como foram tratadas, "
        "(5) Tentativa de fechamento e próximos passos. "
        "Gere um scorecard com notas de 0-10 por critério, pontos fortes, "
        "pontos de melhoria e um plano de ação para a próxima call."
    )
    await update.message.reply_chat_action(ChatAction.TYPING)
    reply = ask_claude(chat_id, "[COMANDO: /analisarcall] Pronto para analisar a call. Cole a transcrição ou resumo.", extra)
    await update.message.reply_text(reply, parse_mode=ParseMode.MARKDOWN)


# MESSAGE HANDLERS

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    await update.message.reply_chat_action(ChatAction.TYPING)
    reply = ask_claude(chat_id, update.message.text)
    await update.message.reply_text(reply, parse_mode=ParseMode.MARKDOWN)


async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    await update.message.reply_chat_action(ChatAction.TYPING)
    audio = update.message.voice or update.message.audio
    if not audio:
        await update.message.reply_text("\u274c Não consegui processar o áudio.")
        return
    file = await context.bot.get_file(audio.file_id)
    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
        await file.download_to_drive(tmp.name)
        tmp_path = tmp.name
    try:
        with open(tmp_path, "rb") as audio_file:
            transcription = groq_client.audio.transcriptions.create(
                model="whisper-large-v3",
                file=audio_file,
                language="pt",
            )
        transcript = transcription.text
        await update.message.reply_text(
            f"\ud83c\udfa4 *Transcrição:*\n_{transcript}_",
            parse_mode=ParseMode.MARKDOWN,
        )
        reply = ask_claude(chat_id, transcript)
        await update.message.reply_text(reply, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        logger.error(f"Erro ao transcrever áudio: {e}")
        await update.message.reply_text("\u274c Erro ao transcrever o áudio. Tente novamente.")
    finally:
        Path(tmp_path).unlink(missing_ok=True)


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    await update.message.reply_chat_action(ChatAction.TYPING)
    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
        await file.download_to_drive(tmp.name)
        tmp_path = tmp.name
    try:
        with open(tmp_path, "rb") as img_file:
            image_data = base64.b64encode(img_file.read()).decode("utf-8")
        caption = update.message.caption or "Analise esta imagem e me diga o que vê."
        response = anthropic_client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": image_data}},
                {"type": "text", "text": caption},
            ]}],
        )
        reply = response.content[0].text
        add_to_history(chat_id, "user", f"[Imagem enviada] {caption}")
        add_to_history(chat_id, "assistant", reply)
        await update.message.reply_text(reply, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        logger.error(f"Erro ao processar foto: {e}")
        await update.message.reply_text("\u274c Erro ao processar a imagem.")
    finally:
        Path(tmp_path).unlink(missing_ok=True)


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    doc = update.message.document
    await update.message.reply_chat_action(ChatAction.TYPING)
    file = await context.bot.get_file(doc.file_id)
    suffix = Path(doc.file_name or "arquivo").suffix.lower()
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        await file.download_to_drive(tmp.name)
        tmp_path = tmp.name
    try:
        content = ""
        if suffix == ".pdf":
            content = _extract_pdf(tmp_path)
        elif suffix in (".xlsx", ".xls"):
            content = _extract_excel(tmp_path)
        elif suffix == ".csv":
            content = _extract_csv(tmp_path)
        else:
            await update.message.reply_text(
                f"\ud83d\udcce Formato `{suffix}` não suportado.\nEnvie arquivos *PDF*, *Excel (.xlsx)* ou *CSV*.",
                parse_mode=ParseMode.MARKDOWN,
            )
            return
        if not content.strip():
            await update.message.reply_text("\u274c Não consegui extrair conteúdo do arquivo.")
            return
        caption = update.message.caption or f"Analise este arquivo: {doc.file_name}"
        user_msg = f"{caption}\n\n--- CONTEÚDOM DO ARQUIVO: {doc.file_name} ---\n{content[:6000]}"
        await update.message.reply_text(
            f"\ud83d\udcc4 Arquivo *{doc.file_name}* recebido. Analisando...",
            parse_mode=ParseMode.MARKDOWN,
        )
        reply = ask_claude(chat_id, user_msg)
        await update.message.reply_text(reply, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        logger.error(f"Erro ao processar documento: {e}")
        await update.message.reply_text("\u274c Erro ao processar o documento.")
    finally:
        Path(tmp_path).unlink(missing_ok=True)


# DOCUMENT EXTRACTORS

def _extract_pdf(path: str) -> str:
    pages = []
    with open(path, "rb") as f:
        reader = PyPDF2.PdfReader(f)
        for page in reader.pages:
            text = page.extract_text()
            if text:
                pages.append(text)
    return "\n\n".join(pages)


def _extract_excel(path: str) -> str:
    dfs = pd.read_excel(path, sheet_name=None)
    parts = []
    for sheet_name, df in dfs.items():
        parts.append(f"### Aba: {sheet_name}\n{df.to_string(index=False)}")
    return "\n\n".join(parts)


def _extract_csv(path: str) -> str:
    df = pd.read_csv(path)
    return df.to_string(index=False)


# ERROR HANDLER

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(f"Erro no update: {context.error}", exc_info=context.error)


# MAIN

def main() -> None:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("limpar", limpar))
    app.add_handler(CommandHandler("diagnostico", diagnostico_cmd))
    app.add_handler(CommandHandler("sdr", sdr_cmd))
    app.add_handler(CommandHandler("proposta", proposta_cmd))
    app.add_handler(CommandHandler("analisarcall", analisarcall_cmd))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_audio))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))

    app.add_error_handler(error_handler)

    async def post_init(application: Application) -> None:
        await application.bot.set_my_commands([
            BotCommand("start",        "Apresentação e menu de funcionalidades"),
            BotCommand("diagnostico",  "Diagnóstico FSS do cliente"),
            BotCommand("sdr",          "Coach de SDR com scripts prontos"),
            BotCommand("proposta",     "Gerador de proposta comercial"),
            BotCommand("analisarcall", "Análise de call de vendas"),
            BotCommand("limpar",       "Limpar histórico da conversa"),
        ])

    app.post_init = post_init

    logger.info("\u2705 Clara Bot iniciado com sucesso!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
