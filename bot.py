import os
import logging
import tempfile
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import anthropic
from groq import Groq
import PyPDF2
import pandas as pd
from openai import OpenAI
import httpx

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

telegram_token = os.environ["TELEGRAM_BOT_TOKEN"]
anthropic_client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
groq_client = Groq(api_key=os.environ["GROQ_API_KEY"])
openai_client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

conversation_history: dict = {}

SYSTEM_PROMPT = """Você é Clara, assistente estratégica pessoal de Angelo Zambom Netto, Head Comercial da TRILIA, operando via contrato de serviço com a Essencia Marketing LTDA através da sua empresa Angelo Zambom Netto LTDA. Você está integrada ao Telegram dele.

Responda sempre em português brasileiro, de forma clara, direta e orientada a resultado. Zambom não precisa de rodeios — seja objetiva e acionável.

Quando o usuário pedir para CRIAR, GERAR ou FAZER uma imagem, ilustração, foto ou visual, responda EXATAMENTE neste formato:
GERAR_IMAGEM: [descrição detalhada em inglês para o DALL-E]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CONTEXTO DO NEGÓCIO
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

A TRILIA é uma consultoria comercial que estrutura operações de vendas de pequenas empresas prestadoras de serviços em um programa de 12 semanas.

Zambom lidera o time comercial (SDRs e Closers), sendo responsável por métricas de prospecção, funil e receita.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
METODOLOGIA FSS — 5 PILARES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. Funis — estrutura e mapeamento dos estágios de venda
2. Pré-Vendas (SDRs) — prospecção, qualificação e agendamento
3. Vendas (Closers) — condução e fechamento
4. Arquitetura de Produtos — estrutura de ofertas por nível
5. Pós-Vendas — retenção, expansão e sucesso do cliente

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ARQUITETURA DE PRODUTOS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

- Front End: produto de entrada, ticket baixo, porta de entrada do funil
- Back End: oferta principal, maior volume de receita
- High End: done-for-you, maior ticket, atendimento premium

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ESTRUTURA DE FECHAMENTO
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. Ancoragem — preço de tabela (referência alta)
2. Preço promocional — ~20% abaixo da tabela
3. Bônus de decisão imediata — incentivo para fechar na hora
4. Última condição — desconto adicional de 5-7% como recurso final
5. Armas de fechamento — urgência, escassez, prova social, garantia

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
KPIs DO FUNIL COMERCIAL
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

- Taxa de agendamento: 15% a 25%
- Taxa de comparecimento: acima de 65%
- Taxa de conversão (Closer): 20% a 35%
- ROAS mínimo: acima de 7
- CAC: monitorado por canal

Dimensionamento MVP: 1 SDR + 1 Closer
CRM: Go High Level com pipelines de Pré-Vendas, Vendas e CS

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
METAS MENSAIS (3 NÍVEIS)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

- Base: meta mínima, garante a operação
- Agressiva: meta padrão de performance
- Ambiciosa: meta de excelência com bônus

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PROPOSTA ATIVA
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Areia que Canta — Treinamento de Alta Performance e Liderança + CIS Assessment
- Opção A: 10 gerentes por R$9.000
- Opção B: 23 gestores e líderes por R$19.500
- Formato presencial, 1 dia (4h treinamento + 4h CIS Assessment)
- Status: aguardando retorno

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FRAMEWORK HORMOZI — $100M OFFERS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

GRAND SLAM OFFER — oferta irrecusável que elimina objeções antes de surgirem

Equação de Valor (Value Equation):
Valor = (Sonho x Probabilidade Percebida) / (Tempo x Esforço)
- Aumentar: resultado desejado + probabilidade de sucesso
- Diminuir: tempo até o resultado + esforço/sacrifício necessário

Construção da oferta:
1. Identificar o sonho do cliente (resultado final desejado)
2. Listar todos os obstáculos entre ele e o sonho
3. Transformar cada obstáculo em uma solução (entregável)
4. Empilhar os entregáveis em uma oferta irrecusável
5. Nomear a oferta de forma que comunique a transformação

Precificação:
- Precificar por valor entregue, nunca por custo ou tempo
- Quanto maior o problema resolvido, maior o ticket justo
- Oferta premium justifica preço premium — nunca competir por preço

Stacking de bônus:
- Cada bônus deve resolver uma objeção específica
- Bônus devem ter valor percebido maior que o preço total
- Criar escassez real (vagas, prazo, condição)

Garantias:
- Garantia incondicional elimina risco do cliente
- Quanto mais forte a garantia, maior a conversão
- Quem tem resultado real não teme oferecer garantia

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FRAMEWORK HORMOZI — $100M LEADS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

CORE 4 — canais de aquisição:
1. Orgânico Quente — base existente (ex-clientes, indicações, seguidores)
2. Orgânico Frio — prospecção outbound sem investimento em mídia
3. Pago Quente — anúncios para audiência que já conhece a marca
4. Pago Frio — anúncios para audiência fria, escala máxima

Funil de aquisição:
- Lead Magnet: entrega valor antecipado, capta contato
- Tripwire / Front End: primeira compra de baixo risco
- Core Offer: oferta principal (Back End)
- High Ticket: oferta premium para melhores clientes (High End)

Reativação de base:
- Lista fria é ativo subutilizado
- Campanha de reativação com nova oferta ou novo ângulo
- Ex-clientes convertem 3-5x mais que leads frios

Scripts de outreach (prospecção fria):
- Personalização real (não genérica)
- Foco no problema do prospect, não no produto
- CTA direto e de baixo atrito (reunião, não venda)
- Volume + qualidade = pipeline previsível

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
COMO VOCÊ DEVE AGIR
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

- Análise de funil → use KPIs FSS como referência
- Construção de oferta → aplique Value Equation e Grand Slam Offer
- Estrutura de proposta → use ancoragem + fechamento FSS
- Aquisição de leads → aplique Core 4 do Hormozi
- Relatório do time → métricas de SDR e Closer separadas
- Diagnóstico comercial → use os 5 pilares FSS
- Análise de arquivo → foco comercial, insights acionáveis
- Pedido de imagem → responda com GERAR_IMAGEM: [prompt em inglês]"""

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        f"Olá, {user.first_name}! 👋 Sou a *Clara*, sua assistente estratégica.\n\n"
        "Posso ajudar com:\n"
        "📝 Texto e estratégia comercial\n"
        "🎙️ Áudios\n"
        "📄 PDFs\n"
        "📊 Planilhas Excel e CSV\n"
        "🎨 Geração de imagens\n\n"
        "_Use /limpar para resetar o histórico._",
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
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            messages=conversation_history[user_id]
        )
        assistant_message = response.content[0].text
        conversation_history[user_id].append({"role": "assistant", "content": assistant_message})

        # Verifica se é pedido de imagem
        if assistant_message.startswith("GERAR_IMAGEM:"):
            prompt_imagem = assistant_message.replace("GERAR_IMAGEM:", "").strip()
            await update.message.reply_text("🎨 Gerando imagem...")
            await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="upload_photo")

            img_response = openai_client.images.generate(
                model="dall-e-3",
                prompt=prompt_imagem,
                size="1024x1024",
                quality="standard",
                n=1
            )
            image_url = img_response.data[0].url

            # Baixa e envia a imagem
            img_data = httpx.get(image_url).content
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                tmp.write(img_data)
                tmp_path = tmp.name

            with open(tmp_path, "rb") as img_file:
                await update.message.reply_photo(photo=img_file)

        else:
            if len(assistant_message) > 4096:
                for i in range(0, len(assistant_message), 4096):
                    await update.message.reply_text(assistant_message[i:i+4096])
            else:
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
                texto_pdf = ""
                for page in reader.pages:
                    texto_pdf += page.extract_text() + "\n"

            if not texto_pdf.strip():
                await update.message.reply_text("Não consegui extrair texto deste PDF.")
                return

            texto_pdf = texto_pdf[:15000]
            prompt = f"{caption}\n\n--- CONTEÚDO DO PDF ({doc.file_name}) ---\n{texto_pdf}"
            await update.message.reply_text(f"📄 PDF recebido: *{doc.file_name}*\nAnalisando...", parse_mode="Markdown")
            await processar_mensagem(update, context, prompt)

        elif nome.endswith(".xlsx") or nome.endswith(".xls"):
            with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
                await file.download_to_drive(tmp.name)
                df = pd.read_excel(tmp.name)

            resumo = f"Planilha: {doc.file_name}\nLinhas: {len(df)} | Colunas: {len(df.columns)}\n"
            resumo += f"Colunas: {', '.join(df.columns.astype(str))}\n\n"
            resumo += df.head(50).to_string(index=False)

            prompt = f"{caption}\n\n--- DADOS DA PLANILHA ---\n{resumo}"
            await update.message.reply_text(f"📊 Planilha recebida: *{doc.file_name}*\nAnalisando...", parse_mode="Markdown")
            await processar_mensagem(update, context, prompt)

        elif nome.endswith(".csv"):
            with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
                await file.download_to_drive(tmp.name)
                df = pd.read_csv(tmp.name)

            resumo = f"Arquivo: {doc.file_name}\nLinhas: {len(df)} | Colunas: {len(df.columns)}\n"
            resumo += f"Colunas: {', '.join(df.columns.astype(str))}\n\n"
            resumo += df.head(50).to_string(index=False)

            prompt = f"{caption}\n\n--- DADOS DO CSV ---\n{resumo}"
            await update.message.reply_text(f"📊 CSV recebido: *{doc.file_name}*\nAnalisando...", parse_mode="Markdown")
            await processar_mensagem(update, context, prompt)

        elif nome.endswith(".txt") or nome.endswith(".md"):
            with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as tmp:
                await file.download_to_drive(tmp.name)
                with open(tmp.name, "r", encoding="utf-8", errors="ignore") as f:
                    conteudo = f.read()[:15000]

            prompt = f"{caption}\n\n--- CONTEÚDO DO ARQUIVO ---\n{conteudo}"
            await update.message.reply_text(f"📝 Arquivo recebido: *{doc.file_name}*\nAnalisando...", parse_mode="Markdown")
            await processar_mensagem(update, context, prompt)

        else:
            await update.message.reply_text(
                f"Formato não suportado.\n\nSuporto: PDF, Excel (.xlsx), CSV, TXT",
                parse_mode="Markdown"
            )

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
