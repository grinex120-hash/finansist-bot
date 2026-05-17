import sys
import os
import logging
from flask import Flask, request, abort
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler
from config import TELEGRAM_TOKEN
from db import init_db
from knowledge import index_documents
from handlers import start, help_command, inline_button_handler, handle_message
from scheduler import start_scheduler, stop_scheduler

# --- Настройки ---
WEBHOOK_SECRET = os.environ.get('WEBHOOK_SECRET', 'MySuperSecretKey123')

# --- Инициализация БД и базы знаний ---
init_db()
index_documents()

# --- Создание приложения Telegram ---
app = Application.builder().token(TELEGRAM_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("help", help_command))
app.add_handler(CallbackQueryHandler(inline_button_handler))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

# --- Flask приложение ---
flask_app = Flask(__name__)

# Запускаем планировщик (для напоминаний и отчётов) при старте
scheduler = start_scheduler(app)

@flask_app.route('/', methods=['GET'])
def index():
    """Для проверки, что сервер жив."""
    return "Бот Финансист работает!", 200

@flask_app.route(f'/{WEBHOOK_SECRET}', methods=['POST'])
async def webhook():
    """Принимает обновления от Telegram."""
    if request.method == 'POST':
        # Проверка секретного токена (опционально, но повышает безопасность)
        secret = request.headers.get('X-Telegram-Bot-Api-Secret-Token')
        if secret and secret != WEBHOOK_SECRET:
            abort(403)
        
        json_data = request.get_json(force=True)
        update = Update.de_json(json_data, app.bot)
        await app.process_update(update)
        return 'ok', 200
    return 'Method Not Allowed', 405

@flask_app.route('/keep_alive', methods=['GET'])
def keep_alive():
    """Эндпоинт для внешнего будильника (cron-job.org)."""
    return "OK", 200

# Для локального тестирования (опционально)
if __name__ == '__main__':
    flask_app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))