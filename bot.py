import os
import logging
import tempfile
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import anthropic
from groq import Groq

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

telegram_token = os.environ["TELEGRAM_BOT_TOKEN"]
anthropic_client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
groq_client = Groq(api_key=os.environ["GROQ_API_KEY"])

conversation_history: dict = {}

SYSTEM_PROMPT = """Você é Clara, uma assistente inteligente e objetiva integrada ao Telegram. 
Responda sempre em português brasileiro, de forma clara e direta.
Você pode ajudar com estratégia comercial, vendas, redação, análises, código, e qualquer outra tarefa."""

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        f"Olá, {user.first_name}! 👋 Sou a *Clara*, sua assistente com IA.\n\n"
        "Pode me mandar mensagem de texto ou áudio — estou aqui pra ajudar!\n\n"
        "_Use /limpar para resetar o histórico da conversa._",
        parse_mode="Markdown"
    )

async def limpar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conversation_history[user_id] = []
    await update.message.reply_text("✅ Histórico limpo! Começando uma nova conversa.")

async def processar_mensagem(update: Update, context: ContextTypes.DEFAULT_TYPE, texto: str):
    user_id = update.effective_user.id

    if user_id not in conversation_history:
        conversation_history[user_id] = []

    conversation_history[user_id].append({"role": "user", "content": texto})

    if len(conversation_history[user_id]) > 20:
        conversation_history[user_id] = conversation_history[user_id][-20:]

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    try:
        response = anthropic_client.messages.create(
            model="claude-opus-4-5",
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=conversation_history[user_id]
        )
        assistant_message = response.content[0].text
        conversation_history[user_id].append({"role": "assistant", "content": assistant_message})
        await update.message.reply_text(assistant_message)

    except Exception as e:
        logger.error(f"Erro ao chamar API: {e}")
        await update.message.reply_text("Ocorreu um erro ao processar sua mensagem. Tente novamente.")

async def responder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await processar_mensagem(update, context, update.message.text)

async def responder_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    try:
        voice = update.message.voice or update.message.audio
        file = await context.bot.get_file(voice.file_id)

        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
            await file.download_to_drive(tmp.name)
            with open(tmp.name, "rb") as audio_file:
                transcricao = groq_client.audio.transcriptions.create(
                    file=("audio.ogg", audio_file),
                    model="whisper-large-v3",
                    language="pt"
                )

        texto = transcricao.text.strip()

        if not texto:
            await update.message.reply_text("Não consegui entender o áudio. Pode repetir?")
            return

        await update.message.reply_text(f"🎙️ *Entendi:* _{texto}_", parse_mode="Markdown")
        await processar_mensagem(update, context, texto)

    except Exception as e:
        logger.error(f"Erro ao processar áudio: {e}")
        await update.message.reply_text("Erro ao processar o áudio. Tente novamente.")

def main():
    app = ApplicationBuilder().token(telegram_token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("limpar", limpar))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, responder_audio))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, responder))
    logger.info("Bot Clara iniciado com suporte a áudio!")
    app.run_polling()

if __name__ == "__main__":
    main()
