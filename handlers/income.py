from telegram import Update
from telegram.ext import ContextTypes
import db
import keyboards

async def handle_income(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    """Обработка доходов (+сумма описание) и целевых операций (*сумма описание)."""
    user_id = update.effective_user.id
    try:
        parts = text[1:].split(maxsplit=1)
        amount = float(parts[0])
        desc = parts[1] if len(parts) > 1 else "без описания"
        
        if text.startswith("+"):
            db.add_income_entry(user_id, amount, desc)
            await update.message.reply_text(f"🎉 Доход {amount:.0f} ₽ ({desc}) успешно записан!", reply_markup=keyboards.get_main_keyboard())
        elif text.startswith("*"):
            db.add_expense_transaction(user_id, amount, desc, "другое")
            # Пополнение цели по ключевому слову
            for word in desc.split():
                goal_row = db.find_goal_by_keyword(user_id, word)
                if goal_row:
                    db.increase_goal_saved(goal_row[0], amount)
                    break
            await update.message.reply_text(f"🎯 Целевая операция {amount:.0f} ₽ ({desc}) записана!", reply_markup=keyboards.get_main_keyboard())
    except:
        await update.message.reply_text("🙈 Не понял. Пример: `+5000 зарплата` или `*5000 на мечту`", reply_markup=keyboards.get_main_keyboard())