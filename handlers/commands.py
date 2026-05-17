from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import ContextTypes
import db
import keyboards
from .onboarding import ensure_onboarding
from .summary import get_main_summary

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    settings = db.get_user_settings(user_id)
    first_name = settings.get('first_name', '')

    hour = datetime.now().hour
    if 6 <= hour < 12:
        time_greeting = "☀️ Доброе утро"
    elif 12 <= hour < 18:
        time_greeting = "🌤 Добрый день"
    elif 18 <= hour < 23:
        time_greeting = "🌆 Добрый вечер"
    else:
        time_greeting = "🌙 Доброй ночи"

    profile = db.get_user_profile(user_id)
    if not profile:
        hello = (
            f"{time_greeting}{f', {first_name}' if first_name else ''}! 👋\n\n"
            "Я – твой личный финансовый помощник, и я искренне рад быть рядом 🤗\n"
            "Вместе мы наведём порядок в твоих финансах, чтобы ты мог(ла) тратить с умом, "
            "копить на мечты и чувствовать себя уверенно каждый день.\n\n"
            "💰 Вот что я умею:\n"
            "• Записывать доходы и расходы одной строкой\n"
            "• Планировать бюджет и ставить финансовые цели\n"
            "• Помогать гасить долги и следить за кредитами\n"
            "• Участвовать в челленджах и откладывать деньги\n"
            "• Давать советы на основе проверенных книг 📚\n\n"
            "Просто вводи `+5000 зарплата`, `-350 обед` или давай сразу настроим твой профиль!"
        )
        await update.message.reply_text(hello, reply_markup=keyboards.get_main_keyboard())
        # Запускаем онбординг – теперь с автоматическим первым вопросом
        await ensure_onboarding(user_id, context)
        return

    hello = f"{time_greeting}{f', {first_name}' if first_name else ''}! "
    await update.message.reply_text(hello, reply_markup=keyboards.get_main_keyboard())

    summary = get_main_summary(user_id)
    if summary:
        await update.message.reply_text(summary, parse_mode="Markdown", reply_markup=keyboards.get_main_keyboard())


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "ℹ️ *Возможности:*\n"
        "• 💰 Доход / 💸 Расход — через быстрый ввод (+ / -)\n"
        "• 👤 Профиль — статистика, регулярные, инструменты\n"
        "• 📚 Знания — советы из книг\n"
        "• 🔧 Инструменты — челленджи, график, кредитный калькулятор, финразбор\n"
        "• ❓ Помощь — это сообщение",
        parse_mode="Markdown", reply_markup=keyboards.get_main_keyboard()
    )