import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import anthropic

# ─── CONFIGURAÇÕES ────────────────────────────────────────────────
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")   # cole seu token aqui ou use variável de ambiente
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")  # sua chave da Anthropic

# ─── SETUP ────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# Histórico de conversa por usuário (em memória)
historico: dict[int, list] = {}

SYSTEM_PROMPT = """Você é Clara, uma assistente inteligente e objetiva integrada ao Telegram. 
Responda sempre em português brasileiro, de forma clara e direta.
Você pode ajudar com análises, redação, estratégia comercial, planilhas, e qualquer outra tarefa."""

# ─── HANDLERS ─────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user.first_name
    historico[update.effective_user.id] = []
    await update.message.reply_text(
        f"Olá, {user}! 👋 Sou a Clara, sua assistente IA.\n\n"
        "Pode me mandar qualquer pergunta ou tarefa. Digite /limpar para reiniciar nossa conversa."
    )

async def limpar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    historico[update.effective_user.id] = []
    await update.message.reply_text("✅ Conversa reiniciada! Como posso te ajudar?")

async def responder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    texto = update.message.text

    # Inicializa histórico do usuário se não existir
    if user_id not in historico:
        historico[user_id] = []

    # Adiciona mensagem do usuário ao histórico
    historico[user_id].append({"role": "user", "content": texto})

    # Limita histórico a 20 mensagens para controlar tokens
    if len(historico[user_id]) > 20:
        historico[user_id] = historico[user_id][-20:]

    # Mostra "digitando..."
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    try:
        resposta = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=historico[user_id]
        )

        texto_resposta = resposta.content[0].text

        # Adiciona resposta da IA ao histórico
        historico[user_id].append({"role": "assistant", "content": texto_resposta})

        await update.message.reply_text(texto_resposta)

    except Exception as e:
        logger.error(f"Erro: {e}")
        await update.message.reply_text("⚠️ Ocorreu um erro. Tente novamente em instantes.")

# ─── MAIN ──────────────────────────────────────────────────────────
def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("limpar", limpar))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, responder))
    logger.info("Bot Clara iniciado ✅")
    app.run_polling()

if __name__ == "__main__":
    main()
