from telegram import Update
from telegram.ext import ContextTypes
from datetime import datetime
import db
import keyboards
import utils

async def handle_expense(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    """Обработка расходов (-сумма описание)."""
    user_id = update.effective_user.id
    try:
        parts = text[1:].split(maxsplit=1)
        amount = float(parts[0])
        desc = parts[1] if len(parts) > 1 else "без описания"
        cat = utils.categorize_expense(desc)
        db.add_expense_transaction(user_id, amount, desc, cat)

        # Проверка лимитов
        month = datetime.now().strftime('%Y-%m')
        limit = db.check_category_limit(user_id, cat, month)
        if limit:
            spent = db.get_current_spending_by_category(user_id, cat, month)
            if spent >= limit:
                await update.message.reply_text(f"🚨 Лимит по «{cat}» превышен! ({limit} ₽)", reply_markup=keyboards.get_main_keyboard())
            elif spent >= limit * 0.8:
                await update.message.reply_text(f"🔸 80% лимита по «{cat}» достигнуто.", reply_markup=keyboards.get_main_keyboard())

        # Проверка челленджей на воздержание
        challenges = db.get_active_challenges(user_id)
        for c in challenges:
            if c[2] == 'avoid_spending' and c[4] and cat.lower() == c[4].lower():
                await context.bot.send_message(
                    user_id,
                    f"⚠️ Эта трата нарушает ваш челлендж «{c[1]}» (воздержание от «{cat}»). Будьте внимательны!",
                    reply_markup=keyboards.get_main_keyboard()
                )

        # Автосписание долга
        if cat == "кредиты/долги":
            for word in desc.split():
                debt_row = db.find_debt_by_keyword(user_id, word)
                if debt_row:
                    db.decrease_debt_balance(debt_row[0], amount)
                    break

        await update.message.reply_text(f"📌 Расход {amount:.0f} ₽ ({desc}) записан.", reply_markup=keyboards.get_main_keyboard())
    except:
        await update.message.reply_text("🙈 Ошибочка. Пример: `-350 обед`", reply_markup=keyboards.get_main_keyboard())