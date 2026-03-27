import os
import logging
import tempfile
import json
from datetime import datetime
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import anthropic
from groq import Groq
import PyPDF2
import pandas as pd
from openai import OpenAI
import httpx
import gspread
from google.oauth2.service_account import Credentials

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

telegram_token = os.environ["TELEGRAM_BOT_TOKEN"]
anthropic_client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
groq_client = Groq(api_key=os.environ["GROQ_API_KEY"])
openai_client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

SPREADSHEET_ID = "1aM5cU7zByL6UF9wSEHTEl1nnr83FwSDS6mOLNTTlsgg"
google_creds_json = os.environ["GOOGLE_CREDENTIALS_JSON"]
creds_dict = json.loads(google_creds_json)
scopes = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
sheets_client = gspread.authorize(creds)

conversation_history: dict = {}

SYSTEM_PROMPT = """Você é Clara, assistente estratégica pessoal de Angelo Zambom Netto, Head Comercial da TRILIA. Você está integrada ao Telegram dele.

Responda sempre em português brasileiro, de forma clara, direta e orientada a resultado. Zambom não precisa de rodeios.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
COMANDOS ESPECIAIS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Quando pedir para CRIAR/GERAR imagem:
GERAR_IMAGEM: [descrição detalhada em inglês]

Quando pedir para REGISTRAR dados do time:
REGISTRAR_DADOS: {"data": "DD/MM/AAAA", "vendedor": "Nome", "empresas": 0, "conversas": 0, "reunioes": 0, "fechamentos": 0, "receita": 0}
Vendedores válidos: Lucas, Iago Quesada, Andreia (SDR). Se data não mencionada, use hoje.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MODO: DIAGNÓSTICO DE CLIENTE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Ativado quando Zambom descrever um prospect ou cliente e pedir diagnóstico, análise ou avaliação.

Execute sempre nesta sequência:
1. PERFIL DO CLIENTE — segmento, porte, maturidade comercial
2. DIAGNÓSTICO FSS — avalie cada pilar (Funis, Pré-Vendas, Vendas, Produto, Pós-Vendas) com nota de 1-5 e justificativa
3. PILAR CRÍTICO — identifique o gargalo principal que trava o crescimento
4. OFERTA RECOMENDADA — qual tier encaixa (Front End / Back End / High End) e por quê
5. OBJEÇÕES PROVÁVEIS — liste as 3 principais e como contornar cada uma
6. PRÓXIMO PASSO — ação concreta para avançar com esse cliente

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MODO: COACH DE SDR
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Ativado quando um SDR (ou Zambom pelo SDR) mandar uma mensagem recebida de lead e pedir como responder, ou pedir script de abordagem.

Execute sempre nesta sequência:
1. LEITURA DO ESTÁGIO — identifique onde o lead está no funil (frio, morno, quente, objeção, silêncio)
2. INTENÇÃO DA RESPOSTA — o que queremos que o lead faça após ler nossa mensagem
3. SCRIPT PRONTO — escreva a mensagem exata para enviar, no tom adequado (WhatsApp/LinkedIn/Email)
4. VARIAÇÃO B — ofereça uma segunda versão mais curta ou com ângulo diferente
5. ALERTA — aponte erros comuns a evitar nesse estágio

Para abordagem fria: use o framework Hormozi — personalização real, foco no problema do prospect, CTA de baixo atrito.
Para follow-up: use escassez, prova social ou nova perspectiva de valor.
Para objeção: valide, reformule e redirecione para o resultado.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MODO: GERADOR DE PROPOSTA
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Ativado quando Zambom pedir para gerar, montar ou criar uma proposta comercial.

Execute sempre nesta sequência:
1. CABEÇALHO — nome do cliente, data, responsável (Zambom / TRILIA)
2. DIAGNÓSTICO — problema identificado no cliente (2-3 linhas)
3. SOLUÇÃO — o que será entregue, em quanto tempo, com qual metodologia (FSS)
4. ARQUITETURA DE OFERTA — apresente 2 opções:
   - Opção A: escopo menor, ticket mais acessível
   - Opção B: escopo completo, ticket maior (ancoragem)
5. TABELA DE PREÇOS — preço de tabela → preço promocional (~20% off) → condição de decisão imediata
6. BÔNUS — 2-3 bônus que resolvem objeções específicas
7. GARANTIA — condição de garantia que elimina risco do cliente
8. PRÓXIMOS PASSOS — o que acontece após o "sim"

Use linguagem direta, orientada a resultado. Evite juridiquês ou linguagem corporativa genérica.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CONTEXTO DO NEGÓCIO
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

TRILIA é uma consultoria comercial que estrutura operações de vendas em 12 semanas.
Zambom é Head Comercial, lidera SDRs e Closers.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
METODOLOGIA FSS — 5 PILARES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. Funis — estrutura e mapeamento dos estágios
2. Pré-Vendas (SDRs) — prospecção, qualificação, agendamento
3. Vendas (Closers) — condução e fechamento
4. Arquitetura de Produtos — Front End / Back End / High End
5. Pós-Vendas — retenção, expansão, sucesso do cliente

KPIs: agendamento 15-25% | comparecimento >65% | conversão 20-35% | ROAS >7

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ESTRUTURA DE FECHAMENTO
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. Ancoragem — preço de tabela alto
2. Preço promocional — ~20% off
3. Bônus de decisão imediata
4. Última condição — 5-7% extra
5. Armas: urgência, escassez, prova social, garantia

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FRAMEWORK HORMOZI
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

$100M OFFERS — Grand Slam Offer:
Valor = (Sonho x Probabilidade) / (Tempo x Esforço)
Construção: sonho → obstáculos → soluções → oferta irrecusável → nome que comunica transformação
Precificação por valor. Stacking de bônus. Garantias fortes.

$100M LEADS — Core 4:
1. Orgânico Quente — base existente
2. Orgânico Frio — outbound sem mídia
3. Pago Quente — anúncios para audiência conhecida
4. Pago Frio — escala máxima

Funil: Lead Magnet → Front End → Back End → High End
Scripts de outreach: personalização real, foco no problema, CTA de baixo atrito."""

def registrar_na_planilha(dados: dict) -> str:
    try:
        sheet = sheets_client.open_by_key(SPREADSHEET_ID)
        aba = sheet.worksheet("Dados")

        data_str = dados.get("data", datetime.now().strftime("%d/%m/%Y"))
        try:
            data_obj = datetime.strptime(data_str, "%d/%m/%Y")
            data_formatada = data_obj.strftime("%Y-%m-%d")
        except:
            data_formatada = data_str

        nova_linha = [
            data_formatada,
            dados.get("vendedor", ""),
            dados.get("empresas", 0),
            dados.get("conversas", 0),
            dados.get("reunioes", 0),
            dados.get("fechamentos", 0),
            dados.get("receita", 0)
        ]

        aba.append_row(nova_linha)
        return f"✅ Registrado!\n📅 {data_str} | 👤 {dados.get('vendedor')}\n📞 {dados.get('empresas')} contatos | 💬 {dados.get('conversas')} conversas | 📅 {dados.get('reunioes')} reuniões | 🤝 {dados.get('fechamentos')} fechamentos | 💰 R${dados.get('receita')}"
    except Exception as e:
        logger.error(f"Erro ao registrar na planilha: {e}")
        return f"❌ Erro ao registrar: {str(e)}"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        f"Olá, {user.first_name}! 👋 Sou a *Clara*, sua assistente estratégica.\n\n"
        "Posso ajudar com:\n"
        "📝 Estratégia e propostas comerciais\n"
        "🔍 Diagnóstico de clientes (FSS)\n"
        "🎯 Coach de SDR — scripts e respostas\n"
        "📄 Análise de PDFs e planilhas\n"
        "🎙️ Áudios\n"
        "🎨 Geração de imagens\n"
        "📋 Registrar dados na planilha\n\n"
        "_Use /limpar para resetar o histórico._",
        parse_mode="Markdown"
    )

async def limpar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conversation_history[user_id] = []
    await update.message.reply_text("✅ Histórico limpo!")

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
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            messages=conversation_history[user_id]
        )
        assistant_message = response.content[0].text
        conversation_history[user_id].append({"role": "assistant", "content": assistant_message})

        if assistant_message.startswith("GERAR_IMAGEM:"):
            prompt_imagem = assistant_message.replace("GERAR_IMAGEM:", "").strip()
            await update.message.reply_text("🎨 Gerando imagem...")
            await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="upload_photo")
            img_response = openai_client.images.generate(
                model="dall-e-3", prompt=prompt_imagem, size="1024x1024", quality="standard", n=1
            )
            img_data = httpx.get(img_response.data[0].url).content
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                tmp.write(img_data)
                tmp_path = tmp.name
            with open(tmp_path, "rb") as img_file:
                await update.message.reply_photo(photo=img_file)

        elif assistant_message.startswith("REGISTRAR_DADOS:"):
            json_str = assistant_message.replace("REGISTRAR_DADOS:", "").strip()
            dados = json.loads(json_str)
            resultado = registrar_na_planilha(dados)
            await update.message.reply_text(resultado)

        else:
            if len(assistant_message) > 4096:
                for i in range(0, len(assistant_message), 4096):
                    await update.message.reply_text(assistant_message[i:i+4096])
            else:
                await update.message.reply_text(assistant_message)

    except Exception as e:
        logger.error(f"Erro ao chamar API: {e}")
        await update.message.reply_text("Ocorreu um erro. Tente novamente.")

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
                    file=("audio.ogg", audio_file), model="whisper-large-v3", language="pt"
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

async def responder_documento(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    doc = update.message.document
    nome = doc.file_name.lower() if doc.file_name else ""
    caption = update.message.caption or "Analise este arquivo com foco comercial e forneça insights práticos e acionáveis."
    try:
        file = await context.bot.get_file(doc.file_id)
        if nome.endswith(".pdf"):
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                await file.download_to_drive(tmp.name)
                reader = PyPDF2.PdfReader(tmp.name)
                texto_pdf = "".join(page.extract_text() + "\n" for page in reader.pages)
            if not texto_pdf.strip():
                await update.message.reply_text("Não consegui extrair texto deste PDF.")
                return
            prompt = f"{caption}\n\n--- PDF: {doc.file_name} ---\n{texto_pdf[:15000]}"
            await update.message.reply_text(f"📄 *{doc.file_name}* recebido. Analisando...", parse_mode="Markdown")
            await processar_mensagem(update, context, prompt)
        elif nome.endswith((".xlsx", ".xls")):
            with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
                await file.download_to_drive(tmp.name)
                df = pd.read_excel(tmp.name)
            resumo = f"Planilha: {doc.file_name}\nLinhas: {len(df)} | Colunas: {', '.join(df.columns.astype(str))}\n\n{df.head(50).to_string(index=False)}"
            await update.message.reply_text(f"📊 *{doc.file_name}* recebida. Analisando...", parse_mode="Markdown")
            await processar_mensagem(update, context, f"{caption}\n\n--- PLANILHA ---\n{resumo}")
        elif nome.endswith(".csv"):
            with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
                await file.download_to_drive(tmp.name)
                df = pd.read_csv(tmp.name)
            resumo = f"CSV: {doc.file_name}\nLinhas: {len(df)} | Colunas: {', '.join(df.columns.astype(str))}\n\n{df.head(50).to_string(index=False)}"
            await update.message.reply_text(f"📊 *{doc.file_name}* recebido. Analisando...", parse_mode="Markdown")
            await processar_mensagem(update, context, f"{caption}\n\n--- CSV ---\n{resumo}")
        elif nome.endswith((".txt", ".md")):
            with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as tmp:
                await file.download_to_drive(tmp.name)
                with open(tmp.name, "r", encoding="utf-8", errors="ignore") as f:
                    conteudo = f.read()[:15000]
            await update.message.reply_text(f"📝 *{doc.file_name}* recebido. Analisando...", parse_mode="Markdown")
            await processar_mensagem(update, context, f"{caption}\n\n--- ARQUIVO ---\n{conteudo}")
        else:
            await update.message.reply_text("Formato não suportado. Aceito: PDF, Excel, CSV, TXT.")
    except Exception as e:
        logger.error(f"Erro ao processar documento: {e}")
        await update.message.reply_text("Erro ao processar o arquivo. Tente novamente.")

def main():
    app = ApplicationBuilder().token(telegram_token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("limpar", limpar))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, responder_audio))
    app.add_handler(MessageHandler(filters.Document.ALL, responder_documento))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, responder))
    logger.info("Bot Clara iniciado!")
    app.run_polling()

if __name__ == "__main__":
    main()
