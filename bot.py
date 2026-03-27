import os
import logging
import tempfile
import json
from datetime import datetime
import pytz
from telegram import Update, Bot
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler
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
ZAMBOM_CHAT_ID = 777694173
TIMEZONE = pytz.timezone("America/Sao_Paulo")

google_creds_json = os.environ["GOOGLE_CREDENTIALS_JSON"]
creds_dict = json.loads(google_creds_json)
scopes = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
sheets_client = gspread.authorize(creds)

conversation_history: dict = {}

SYSTEM_PROMPT = """Você é Clara, assistente estratégica pessoal de Angelo Zambom Netto, Head Comercial da TRILIA. Integrada ao Telegram.

Responda sempre em português brasileiro, direto e orientado a resultado.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
COMANDOS ESPECIAIS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Imagem → GERAR_IMAGEM: [descrição em inglês]
Dados do time → REGISTRAR_DADOS: {"data": "DD/MM/AAAA", "vendedor": "Nome", "empresas": 0, "conversas": 0, "reunioes": 0, "fechamentos": 0, "receita": 0}
Vendedores válidos: Lucas, Iago Quesada, Andreia (SDR)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MODO: DIAGNÓSTICO DE CLIENTE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Ativado quando Zambom descrever um prospect e pedir diagnóstico.

1. PERFIL — segmento, porte, maturidade comercial
2. DIAGNÓSTICO FSS — nota 1-5 por pilar com justificativa
3. PILAR CRÍTICO — gargalo principal
4. OFERTA RECOMENDADA — Front End / Back End / High End e por quê
5. OBJEÇÕES PROVÁVEIS — top 3 e como contornar
6. PRÓXIMO PASSO — ação concreta

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MODO: COACH DE SDR
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Ativado quando pedir script, resposta para lead ou abordagem.

1. LEITURA DO ESTÁGIO — frio / morno / quente / objeção / silêncio
2. INTENÇÃO — o que queremos que o lead faça
3. SCRIPT PRONTO — mensagem exata para enviar
4. VARIAÇÃO B — versão alternativa
5. ALERTA — erros comuns a evitar

Framework: personalização real, foco no problema, CTA de baixo atrito.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MODO: GERADOR DE PROPOSTA
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Ativado quando pedir proposta comercial.

1. CABEÇALHO — cliente, data, TRILIA
2. DIAGNÓSTICO — problema identificado (2-3 linhas)
3. SOLUÇÃO — entregas, prazo, metodologia FSS
4. OPÇÕES — Opção A (menor escopo) e Opção B (completo/ancoragem)
5. PREÇOS — tabela → promocional (~20% off) → decisão imediata
6. BÔNUS — 2-3 que resolvem objeções
7. GARANTIA — elimina risco do cliente
8. PRÓXIMOS PASSOS — o que acontece após o sim

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MODO: ANÁLISE DE CALL
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Ativado quando Zambom mandar transcrição ou resumo de uma reunião de vendas e pedir análise.

1. RESUMO EXECUTIVO — o que aconteceu na call em 3 linhas
2. RAPPORT — avalie abertura e conexão com o prospect (nota 1-5)
3. DIAGNÓSTICO DO VENDEDOR — identificou o problema real? Fez as perguntas certas?
4. APRESENTAÇÃO DE VALOR — comunicou resultado ou apenas produto?
5. OBJEÇÕES — como foram tratadas? O que faltou?
6. MOMENTO DO FECHAMENTO — tentou fechar? Como? Usou ancoragem?
7. ERROS CRÍTICOS — máx 3, direto ao ponto
8. O QUE FAZER NA PRÓXIMA CALL — ações concretas para o Closer

Use os benchmarks FSS para avaliar: comparecimento >65%, conversão 20-35%.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CONTEXTO DO NEGÓCIO
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

TRILIA — consultoria comercial, programa de 12 semanas.
Time: SDRs (Lucas, Iago Quesada, Andreia) e Closers.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
METODOLOGIA FSS — 5 PILARES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. Funis
2. Pré-Vendas (SDRs) — agendamento 15-25%
3. Vendas (Closers) — conversão 20-35%, comparecimento >65%
4. Arquitetura — Front End / Back End / High End
5. Pós-Vendas

ROAS >7 | CAC monitorado por canal

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ESTRUTURA DE FECHAMENTO
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Ancoragem → promocional (~20% off) → bônus imediato → última condição (5-7%) → urgência/escassez/prova social/garantia

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
HORMOZI
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

$100M Offers: Valor = (Sonho x Probabilidade) / (Tempo x Esforço)
Grand Slam Offer: sonho → obstáculos → soluções → oferta irrecusável
Precificação por valor. Stacking de bônus. Garantias fortes.

$100M Leads — Core 4: Orgânico Quente / Frio | Pago Quente / Frio
Funil: Lead Magnet → Front End → Back End → High End"""

def gerar_briefing_diario() -> str:
    hoje = datetime.now(TIMEZONE)
    dia_semana = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"][hoje.weekday()]
    data_str = hoje.strftime("%d/%m/%Y")

    try:
        sheet = sheets_client.open_by_key(SPREADSHEET_ID)
        aba_metas = sheet.worksheet("Metas")
        dados_metas = aba_metas.get_all_values()

        aba_dados = sheet.worksheet("Dados")
        dados = aba_dados.get_all_values()

        from datetime import timedelta
        ontem = hoje - timedelta(days=1)
        ontem_str = ontem.strftime("%Y-%m-%d")
        ontem_slash = ontem.strftime("%d/%m/%Y")

        def data_de_ontem(val):
            v = str(val).strip()
            return v.startswith(ontem_str) or v == ontem_slash

        registros_ontem = [r for r in dados[1:] if r and data_de_ontem(r[0])]

        def to_int(v):
            try: return int(float(str(v).replace(',','.')))
            except: return 0

        def to_float(v):
            try: return float(str(v).replace(',','.'))
            except: return 0.0

        por_vendedor = {}
        for r in registros_ontem:
            vendedor = r[1].strip() if r[1] else "Desconhecido"
            if vendedor not in por_vendedor:
                por_vendedor[vendedor] = {"contatos": 0, "conversas": 0, "reunioes": 0, "fechamentos": 0, "receita": 0.0}
            por_vendedor[vendedor]["contatos"] += to_int(r[2])
            por_vendedor[vendedor]["conversas"] += to_int(r[3])
            por_vendedor[vendedor]["reunioes"] += to_int(r[4])
            por_vendedor[vendedor]["fechamentos"] += to_int(r[5])
            por_vendedor[vendedor]["receita"] += to_float(r[6])

        if por_vendedor:
            linhas = [f"Resultado de ontem ({ontem.strftime('%d/%m')}) por vendedor:"]
            for v, d in por_vendedor.items():
                linhas.append(f"• {v}: {d['contatos']} contatos | {d['conversas']} conversas | {d['reunioes']} reuniões | {d['fechamentos']} fechamentos | R${d['receita']:,.0f}")
            resumo_ontem = "\n".join(linhas)
        else:
            resumo_ontem = f"Nenhum registro encontrado para ontem ({ontem.strftime('%d/%m/%Y')}). Pode ser feriado, fim de semana ou dado ainda não lançado."

        # Acumulado do mês
        mes_atual = hoje.strftime("%Y-%m")
        mes_slash = hoje.strftime("%m/%Y")
        def data_do_mes(val):
            v = str(val).strip()
            return v.startswith(mes_atual) or v.endswith(mes_slash) or f"/{hoje.strftime('%m')}/{hoje.year}" in v
        registros_mes = [r for r in dados[1:] if r and data_do_mes(r[0])]
        total_contatos_mes = sum(to_int(r[2]) for r in registros_mes)
        total_reunioes_mes = sum(to_int(r[4]) for r in registros_mes)
        total_fechamentos_mes = sum(to_int(r[5]) for r in registros_mes)
        total_receita_mes = sum(to_float(r[6]) for r in registros_mes)
        resumo_mes = f"Acumulado de {hoje.strftime('%B/%Y')}: {total_contatos_mes} contatos | {total_reunioes_mes} reuniões | {total_fechamentos_mes} fechamentos | R${total_receita_mes:,.0f}"

        resumo_planilha = resumo_ontem + "\n\n" + resumo_mes
    except Exception as e:
        resumo_planilha = f"(não foi possível carregar dados da planilha: {e})"

    prompt_briefing = f"""Gere um briefing diário motivador e estratégico para Zambom, Head Comercial da TRILIA.

Data: {dia_semana}, {data_str}
Dados de ontem por vendedor: {resumo_planilha}

O briefing deve ter:
1. SAUDAÇÃO — curta, com o dia da semana
2. FOCO DO DIA — 1 prioridade comercial clara para hoje
3. RESULTADO DE ONTEM — mostre os números por vendedor, destaque quem se destacou e quem ficou abaixo
4. ACUMULADO DO MÊS — mostre o total do mês e avalie o ritmo: está no caminho certo para bater a meta?
5. DESAFIO DO DIA — 1 ação específica e ousada para o time executar hoje
6. FRASE MOTIVACIONAL — de Hormozi, Cardone ou similar, em português

Seja direto, energético e orientado a resultado. Máximo 20 linhas."""

    try:
        response = anthropic_client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt_briefing}]
        )
        return response.content[0].text
    except Exception as e:
        return f"Erro ao gerar briefing: {e}"

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
        nova_linha = [data_formatada, dados.get("vendedor", ""), dados.get("empresas", 0),
                      dados.get("conversas", 0), dados.get("reunioes", 0),
                      dados.get("fechamentos", 0), dados.get("receita", 0)]
        aba.append_row(nova_linha)
        return f"✅ Registrado!\n📅 {data_str} | 👤 {dados.get('vendedor')}\n📞 {dados.get('empresas')} contatos | 💬 {dados.get('conversas')} conversas | 📅 {dados.get('reunioes')} reuniões | 🤝 {dados.get('fechamentos')} fechamentos | 💰 R${dados.get('receita')}"
    except Exception as e:
        return f"❌ Erro: {str(e)}"

async def enviar_briefing_diario(bot: Bot):
    try:
        logger.info("Gerando briefing diário...")
        briefing = gerar_briefing_diario()
        await bot.send_message(chat_id=ZAMBOM_CHAT_ID, text=f"☀️ *BOM DIA, ZAMBOM!*\n\n{briefing}", parse_mode="Markdown")
        logger.info("Briefing enviado com sucesso!")
    except Exception as e:
        logger.error(f"Erro ao enviar briefing: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        f"Olá, {user.first_name}! 👋 Sou a *Clara*, sua assistente estratégica.\n\n"
        "Posso ajudar com:\n"
        "📝 Estratégia e propostas comerciais\n"
        "🔍 Diagnóstico de clientes (FSS)\n"
        "🎯 Coach de SDR — scripts e respostas\n"
        "📞 Análise de calls de vendas\n"
        "☀️ Briefing diário às 8h (automático)\n"
        "📄 PDFs e planilhas\n"
        "🎙️ Áudios\n"
        "🎨 Imagens\n"
        "📋 Registro de dados na planilha\n\n"
        "_Use /limpar para resetar o histórico._\n"
        "_Use /briefing para gerar agora._",
        parse_mode="Markdown"
    )

async def limpar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conversation_history[user_id] = []
    await update.message.reply_text("✅ Histórico limpo!")

async def cmd_briefing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("☀️ Gerando seu briefing...")
    briefing = gerar_briefing_diario()
    await update.message.reply_text(f"☀️ *BOM DIA, ZAMBOM!*\n\n{briefing}", parse_mode="Markdown")

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
            model="claude-sonnet-4-6", max_tokens=2048, system=SYSTEM_PROMPT,
            messages=conversation_history[user_id]
        )
        assistant_message = response.content[0].text
        conversation_history[user_id].append({"role": "assistant", "content": assistant_message})

        if assistant_message.startswith("GERAR_IMAGEM:"):
            prompt_imagem = assistant_message.replace("GERAR_IMAGEM:", "").strip()
            await update.message.reply_text("🎨 Gerando imagem...")
            await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="upload_photo")
            img_response = openai_client.images.generate(model="dall-e-3", prompt=prompt_imagem, size="1024x1024", quality="standard", n=1)
            img_data = httpx.get(img_response.data[0].url).content
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                tmp.write(img_data)
            with open(tmp.name, "rb") as img_file:
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
        logger.error(f"Erro API: {e}")
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
                transcricao = groq_client.audio.transcriptions.create(file=("audio.ogg", audio_file), model="whisper-large-v3", language="pt")
        texto = transcricao.text.strip()
        if not texto:
            await update.message.reply_text("Não consegui entender o áudio.")
            return
        await update.message.reply_text(f"🎙️ *Entendi:* _{texto}_", parse_mode="Markdown")
        await processar_mensagem(update, context, texto)
    except Exception as e:
        logger.error(f"Erro áudio: {e}")
        await update.message.reply_text("Erro ao processar áudio.")

async def responder_documento(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    doc = update.message.document
    nome = doc.file_name.lower() if doc.file_name else ""
    caption = update.message.caption or "Analise com foco comercial e forneça insights acionáveis."
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
            await update.message.reply_text(f"📄 *{doc.file_name}* recebido. Analisando...", parse_mode="Markdown")
            await processar_mensagem(update, context, f"{caption}\n\n--- PDF ---\n{texto_pdf[:15000]}")
        elif nome.endswith((".xlsx", ".xls")):
            with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
                await file.download_to_drive(tmp.name)
                df = pd.read_excel(tmp.name)
            resumo = f"Linhas: {len(df)} | Colunas: {', '.join(df.columns.astype(str))}\n\n{df.head(50).to_string(index=False)}"
            await update.message.reply_text(f"📊 *{doc.file_name}* recebida. Analisando...", parse_mode="Markdown")
            await processar_mensagem(update, context, f"{caption}\n\n--- PLANILHA ---\n{resumo}")
        elif nome.endswith(".csv"):
            with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
                await file.download_to_drive(tmp.name)
                df = pd.read_csv(tmp.name)
            resumo = f"Linhas: {len(df)} | Colunas: {', '.join(df.columns.astype(str))}\n\n{df.head(50).to_string(index=False)}"
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
        logger.error(f"Erro documento: {e}")
        await update.message.reply_text("Erro ao processar arquivo.")


async def responder_foto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    try:
        foto = update.message.photo[-1]  # maior resolução
        file = await context.bot.get_file(foto.file_id)
        caption = update.message.caption or "Analise esta imagem e forneça insights relevantes."

        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            await file.download_to_drive(tmp.name)
            with open(tmp.name, "rb") as img_file:
                import base64
                img_b64 = base64.b64encode(img_file.read()).decode("utf-8")

        user_id = update.effective_user.id
        if user_id not in conversation_history:
            conversation_history[user_id] = []

        conversation_history[user_id].append({
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": img_b64}},
                {"type": "text", "text": caption}
            ]
        })

        if len(conversation_history[user_id]) > 20:
            conversation_history[user_id] = conversation_history[user_id][-20:]

        response = anthropic_client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            messages=conversation_history[user_id]
        )
        assistant_message = response.content[0].text
        conversation_history[user_id].append({"role": "assistant", "content": assistant_message})

        if len(assistant_message) > 4096:
            for i in range(0, len(assistant_message), 4096):
                await update.message.reply_text(assistant_message[i:i+4096])
        else:
            await update.message.reply_text(assistant_message)

    except Exception as e:
        logger.error(f"Erro ao processar foto: {e}")
        await update.message.reply_text("Erro ao processar a imagem. Tente novamente.")

def main():
    app = ApplicationBuilder().token(telegram_token).build()

    # Agendador do briefing diário às 8h (horário de Brasília)
    scheduler = AsyncIOScheduler(timezone=TIMEZONE)
    scheduler.add_job(
        enviar_briefing_diario,
        trigger="cron",
        hour=8,
        minute=0,
        args=[app.bot]
    )
    scheduler.start()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("limpar", limpar))
    app.add_handler(CommandHandler("briefing", cmd_briefing))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, responder_audio))
    app.add_handler(MessageHandler(filters.PHOTO, responder_foto))
    app.add_handler(MessageHandler(filters.Document.ALL, responder_documento))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, responder))
    logger.info("Bot Clara iniciado com briefing diário!")
    app.run_polling()

if __name__ == "__main__":
    main()
