import re
from telegram import Update
from telegram.ext import ContextTypes
import db
import keyboards
from summary import get_main_summary   # <--- исправлено

async def ensure_onboarding(user_id: int, context: ContextTypes.DEFAULT_TYPE, silent=False, start_message=True):
    profile = db.get_user_profile(user_id)
    if not profile:
        if not silent:
            db.ensure_profile(user_id)
            context.user_data['onboarding'] = True
            context.user_data['onboarding_step'] = 1
            if start_message:
                await context.bot.send_message(
                    user_id,
                    "👋 Давайте настроим ваш финансовый профиль.\n"
                    "Шаг 1/6: Как вас зовут?"
                )
        return False
    return True

async def handle_onboarding(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    step = context.user_data.get('onboarding_step', 0)

    if step == 1:
        db.update_user_setting(user_id, 'first_name', text)
        context.user_data['onboarding_step'] = 2
        await update.message.reply_text(
            f"Приятно познакомиться, {text}!\n"
            "Шаг 2/6: Введите ваш текущий баланс (сколько денег у вас сейчас на руках/картах)."
        )
    elif step == 2:
        try:
            balance = float(text)
            db.record_balance(user_id, balance)
            context.user_data['onboarding_step'] = 3
            await update.message.reply_text(
                "✅ Баланс сохранён.\n"
                "Шаг 3/6: Есть ли у вас регулярные доходы? "
                "Укажите сумму и описание (например, 50000 зарплата) или 'нет'."
            )
        except ValueError:
            await update.message.reply_text("❌ Введите число.")
    elif step == 3:
        if text.lower() == 'нет':
            context.user_data['onboarding_step'] = 4
            await update.message.reply_text(
                "Шаг 4/6: Регулярные расходы? Например, 30000 аренда. Или 'нет'."
            )
        else:
            parts = text.split(maxsplit=1)
            try:
                amount = float(parts[0])
                desc = parts[1] if len(parts) > 1 else "без описания"
                db.add_regular_item(user_id, 'income', amount, desc)
                await update.message.reply_text(
                    "✅ Записал. Если есть ещё регулярные доходы, введите их так же, иначе напишите 'нет'."
                )
            except ValueError:
                await update.message.reply_text("❌ Формат: сумма описание")
    elif step == 4:
        if text.lower() == 'нет':
            context.user_data['onboarding_step'] = 5
            await update.message.reply_text(
                "Шаг 5/6: Какие у вас финансовые цели? Опишите их (например, 'Накопить 200000 на отпуск') или напишите 'нет'."
            )
        else:
            parts = text.split(maxsplit=1)
            try:
                amount = float(parts[0])
                desc = parts[1] if len(parts) > 1 else "без описания"
                db.add_regular_item(user_id, 'expense', amount, desc)
                await update.message.reply_text(
                    "✅ Записал. Если есть ещё регулярные расходы, введите их, иначе 'нет'."
                )
            except ValueError:
                await update.message.reply_text("❌ Формат: сумма описание")
    elif step == 5:
        if text.lower() == 'нет':
            text = ''
        if text:
            db.add_goal(user_id, text, 0, None)
        context.user_data['onboarding_step'] = 6
        await update.message.reply_text(
            "Шаг 6/6: Есть ли у вас долги или кредиты? "
            "Введите данные в формате: Название Сумма Процент Срок(мес) [ЕжемесячныйПлатёж]\n"
            "Пример: Кредит 150000 18 12\n"
            "Или укажите свой платёж: Кредит 150000 18 12 15000\n"
            "Если нет, напишите 'нет'."
        )
    elif step == 6:
        if text.lower() != 'нет':
            name, total, rate, term, monthly = db.parse_debt_input(text)
            db.add_debt(user_id, name, total, rate, term, monthly)

        context.user_data['onboarding'] = False
        context.user_data.pop('onboarding_step', None)

        settings = db.get_user_settings(user_id)
        name = settings.get('first_name', '')

        msg = (
            f"🎉 {name}, твой финансовый профиль настроен! Я помогу тебе управлять деньгами с умом.\n\n"
            "📌 **Что ты можешь делать:**\n"
            "• **Быстрый ввод** – отправляй сообщения `+5000 зарплата`, `-350 кофе` или `=25000 остаток`, чтобы я записывал доходы, расходы и фиксировал баланс.\n"
            "• **Профиль** – в нём собрана вся статистика: доходы, расходы, свободный остаток, прогноз на конец месяца, твои цели и долги.\n"
            "   Из профиля ты можешь управлять регулярными доходами/расходами, планировать платежи, редактировать личные данные, устанавливать лимиты.\n"
            "• **Знания** – задай мне любой вопрос по финансовой грамотности, и я найду ответ в проверенных книгах.\n"
            "• **Инструменты** – здесь живут челленджи (копилки и ограничения), график расходов по категориям, кредитный калькулятор и финансовый разбор твоей ситуации.\n"
            "• **Помощь** – всегда доступна по кнопке, напомнит основные команды и возможности.\n\n"
            "📬 Я буду напоминать о предстоящих платежах, если ты настроишь уведомления.\n"
            "Вся эта информация всегда доступна в разделе **❓ Помощь**.\n\n"
            "А теперь просто начни – введи первую операцию или загляни в профиль!"
        )
        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=keyboards.get_main_keyboard())