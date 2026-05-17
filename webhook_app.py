import os
import logging
from fastapi import FastAPI, Request, Response
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, CallbackQueryHandler
)
from contextlib import asynccontextmanager

from config import TELEGRAM_TOKEN
from db import init_db
from knowledge import index_documents
from handlers import start, help_command, inline_button_handler, handle_message
from scheduler import start_scheduler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Настройки ---
WEBHOOK_SECRET = os.environ.get('WEBHOOK_SECRET', 'MySecret')
# Render автоматически даёт переменную RENDER_EXTERNAL_HOSTNAME
RENDER_HOST = os.environ.get('RENDER_EXTERNAL_HOSTNAME', 'localhost')
WEBHOOK_URL = f"https://{RENDER_HOST}/{WEBHOOK_SECRET}"

# --- Инициализация бота ---
init_db()
index_documents()

ptb_app = Application.builder().token(TELEGRAM_TOKEN).build()
ptb_app.add_handler(CommandHandler("start", start))
ptb_app.add_handler(CommandHandler("help", help_command))
ptb_app.add_handler(CallbackQueryHandler(inline_button_handler))
ptb_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

# Планировщик
scheduler = start_scheduler(ptb_app)  # он запустится в фоне

# --- Lifespan для установки вебхука при старте ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Старт
    await ptb_app.initialize()
    await ptb_app.bot.set_webhook(WEBHOOK_URL, secret_token=WEBHOOK_SECRET)
    logger.info(f"Webhook установлен на {WEBHOOK_URL}")
    yield
    # Остановка
    await ptb_app.bot.delete_webhook()
    await ptb_app.shutdown()
    # Остановка планировщика (опционально, но хорошо бы)
    from scheduler import stop_scheduler
    stop_scheduler()

fastapi_app = FastAPI(lifespan=lifespan)

# --- Эндпоинты ---
@fastapi_app.get("/")
async def root():
    return {"status": "ok"}

@fastapi_app.post(f"/{WEBHOOK_SECRET}")
async def webhook(request: Request):
    # Проверка секретного токена
    secret_token = request.headers.get('X-Telegram-Bot-Api-Secret-Token')
    if secret_token != WEBHOOK_SECRET:
        logger.warning("Invalid secret token")
        return Response(status_code=403)

    data = await request.json()
    update = Update.de_json(data, ptb_app.bot)
    await ptb_app.process_update(update)
    return Response(status_code=200)

@fastapi_app.get("/keep_alive")
async def keep_alive():
    return Response(status_code=200)