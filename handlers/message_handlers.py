# handlers/message_handlers.py
import re
from datetime import datetime
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
import db
import keyboards
from .onboarding import handle_onboarding
from .profile import get_profile_text
from .commands import help_command
from .income import handle_income
from .expense import handle_expense
from .knowledge import handle_knowledge_query
from .ai_dialog import handle_ai_dialog

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    if context.user_data.get('onboarding'):
        return await handle_onboarding(update, context)

    # Отмена любого ожидающего ввода
    if 'awaiting' in context.user_data and text.lower() == 'отмена':
        context.user_data.pop('awaiting', None)
        await update.message.reply_text("❌ Ввод отменён.", reply_markup=keyboards.get_main_keyboard())
        return

    # ================= Быстрый ввод (баланс, доходы, расходы, целевые) =================
    if text.startswith("=") and len(text) > 1:
        try:
            parts = text[1:].split(maxsplit=1)
            balance = float(parts[0])
            desc = parts[1] if len(parts) > 1 else None
            diff = db.record_balance(user_id, balance, desc)
            msg = f"⚖️ Баланс зафиксирован: {balance:.2f} ₽."
            if diff:
                msg += f" Разница с прошлым разом: {diff:+.2f} ₽."
            await update.message.reply_text(msg, reply_markup=keyboards.get_main_keyboard())
        except:
            await update.message.reply_text("🙈 Неправильный формат. Пример: `=5000`", reply_markup=keyboards.get_main_keyboard())
        return

    # Доходы и целевые операции
    if text.startswith(("+", "*")):
        await handle_income(update, context, text)
        return

    # Расходы
    if text.startswith("-"):
        await handle_expense(update, context, text)
        return

    # ================= Главное меню =================
    if text == "👤 Профиль":
        pt, kb = get_profile_text(user_id)
        await update.message.reply_text(pt, parse_mode="Markdown", reply_markup=kb)
        return

    if text == "📚 Знания":
        context.user_data['awaiting'] = 'knowledge_query'
        await update.message.reply_text("📚 Задайте вопрос по финансам, я поищу в книгах.", reply_markup=keyboards.get_main_keyboard())
        return

    if text == "🔧 Инструменты":
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎯 Челленджи", callback_data="challenges_menu")],
            [InlineKeyboardButton("📊 График", callback_data="chart")],
            [InlineKeyboardButton("🏦 Кредитный калькулятор", callback_data="loan_calc_tool")],
            [InlineKeyboardButton("📋 Финразбор", callback_data="financial_analysis")],
        ])
        await update.message.reply_text("🔧 Инструменты:", reply_markup=keyboard)
        return

    if text == "❓ Помощь":
        await help_command(update, context)
        return

    # ================= Обработка состояний (ожиданий ввода) =================
    if 'awaiting' in context.user_data:
        state = context.user_data.pop('awaiting')

        if state == 'knowledge_query':
            await handle_knowledge_query(update, context, text)
            return

        if state == 'challenge_setup':
            parts = text.split()
            if len(parts) < 4:
                await update.message.reply_text("❌ Неверный формат. Пример: `воздержание 0 кофе 2026-06-01`", reply_markup=keyboards.get_main_keyboard())
                return
            try:
                ctype = parts[0].lower()
                target = float(parts[1])
                category = parts[2] if parts[2] != '_' else None
                end_date = parts[3]
                if ctype not in ('воздержание', 'накопление'):
                    raise ValueError
                datetime.strptime(end_date, '%Y-%m-%d')
                db.create_challenge(user_id, f"Челлендж: {ctype}", ctype, target, category, end_date)
                await update.message.reply_text("✅ Челлендж создан! Удачи в выполнении!", reply_markup=keyboards.get_main_keyboard())
            except:
                await update.message.reply_text("❌ Ошибка в данных.", reply_markup=keyboards.get_main_keyboard())
            return

        if state == 'create_challenge':
            context.user_data['awaiting'] = 'challenge_setup'
            await update.message.reply_text("🎯 Введите данные челленджа: `тип сумма категория дата_окончания`\nПример: `воздержание 0 кофе 2026-06-01`")
            return

        if state == 'add_income':
            parts = text.split(maxsplit=1)
            if len(parts) < 2:
                await update.message.reply_text("🙏 Формат: `+сумма описание`", reply_markup=keyboards.get_main_keyboard())
                context.user_data['awaiting'] = 'add_income'
                return
            try:
                amount = float(parts[0])
                desc = parts[1]
                db.add_income_entry(user_id, amount, desc)
                await update.message.reply_text(f"🎉 Доход {amount:.0f} ₽ ({desc}) добавлен!", reply_markup=keyboards.get_main_keyboard())
            except:
                await update.message.reply_text("❌ Сумма должна быть числом.", reply_markup=keyboards.get_main_keyboard())
                context.user_data['awaiting'] = 'add_income'
            return

        if state == 'add_expense':
            parts = text.split(maxsplit=1)
            if len(parts) < 2:
                await update.message.reply_text("🙏 Формат: `-сумма описание`", reply_markup=keyboards.get_main_keyboard())
                context.user_data['awaiting'] = 'add_expense'
                return
            try:
                amount = float(parts[0])
                desc = parts[1]
                cat = "другое"
                db.add_expense_transaction(user_id, amount, desc, cat)
                if cat == "кредиты/долги":
                    for word in desc.split():
                        debt_row = db.find_debt_by_keyword(user_id, word)
                        if debt_row:
                            db.decrease_debt_balance(debt_row[0], amount)
                            break
                await update.message.reply_text(f"📌 Расход {amount:.0f} ₽ ({desc}) записан.", reply_markup=keyboards.get_main_keyboard())
            except:
                await update.message.reply_text("❌ Сумма должна быть числом.", reply_markup=keyboards.get_main_keyboard())
                context.user_data['awaiting'] = 'add_expense'
            return

        if state in ('regular_income', 'regular_expense'):
            parts = text.split(maxsplit=1)
            if len(parts) < 2:
                await update.message.reply_text("🙏 Формат: `сумма описание`", reply_markup=keyboards.get_main_keyboard())
                return
            try:
                amount = float(parts[0])
                desc = parts[1]
                itype = 'income' if state == 'regular_income' else 'expense'
                db.add_regular_item(user_id, itype, amount, desc)
                await update.message.reply_text(f"✅ Регулярный {'доход' if itype=='income' else 'расход'} добавлен.")
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("Да, на конкретные даты", callback_data=f"plan_dates_{itype}_{amount}_{desc}")],
                    [InlineKeyboardButton("Нет, просто регулярная статья", callback_data="cancel_plan")]
                ])
                await update.message.reply_text("Хотите запланировать конкретные платежи и напоминания?", reply_markup=keyboard)
            except:
                await update.message.reply_text("❌ Сумма должна быть числом.", reply_markup=keyboards.get_main_keyboard())
            return

        if state == 'set_limit':
            parts = text.split(maxsplit=1)
            if len(parts) < 2:
                await update.message.reply_text("❌ Формат: `категория сумма`", reply_markup=keyboards.get_main_keyboard())
                return
            try:
                cat = parts[0].lower()
                limit = float(parts[1])
                month = datetime.now().strftime('%Y-%m')
                db.set_category_limit(user_id, cat, limit, month)
                await update.message.reply_text(f"✅ Лимит по «{cat}» установлен: {limit:.0f} ₽", reply_markup=keyboards.get_main_keyboard())
            except:
                await update.message.reply_text("❌ Сумма должна быть числом.", reply_markup=keyboards.get_main_keyboard())
            return

        if state == 'loan_calc':
            parts = text.split()
            if len(parts) != 3:
                await update.message.reply_text("❌ Формат: `сумма ставка срок`", reply_markup=keyboards.get_main_keyboard())
                return
            try:
                S = float(parts[0])
                rate = float(parts[1]) / 100 / 12
                months = int(parts[2])
                if rate == 0:
                    monthly = S / months
                else:
                    monthly = S * rate * (1 + rate)**months / ((1 + rate)**months - 1)
                total = monthly * months
                overpay = total - S
                reply = f"Ежемесячный платёж: {monthly:.2f} ₽\nПереплата: {overpay:.2f} ₽\nОбщая сумма выплат: {total:.2f} ₽"
                await update.message.reply_text(reply, reply_markup=keyboards.get_main_keyboard())
            except:
                await update.message.reply_text("❌ Ошибка. Проверьте числа.")
            return

        if state == 'add_goal':
            parts = text.split(maxsplit=3)
            desc = parts[0]
            target = float(parts[1]) if len(parts) > 1 else 0
            deadline = parts[2] if len(parts) > 2 else None
            db.add_goal(user_id, desc, target, deadline)
            await update.message.reply_text(f"🎯 Цель «{desc}» поставлена! Я буду следить за прогрессом.", reply_markup=keyboards.get_main_keyboard())
            return

        if state == 'add_debt':
            name, total, rate, term, monthly = db.parse_debt_input(text)
            db.add_debt(user_id, name, total, rate, term, monthly)
            await update.message.reply_text(f"🏦 Долг «{name}» записан.", reply_markup=keyboards.get_main_keyboard())
            return

        if state == 'edit_name':
            db.update_user_setting(user_id, 'first_name', text)
            await update.message.reply_text(f"👤 Имя обновлено! Теперь я буду называть вас {text}.", reply_markup=keyboards.get_main_keyboard())
            return

        if state == 'add_payment_manual':
            match = re.match(r'(.+)\s+([\d.]+)\s+(\d{4}-\d{2}-\d{2})(?:,(\d+))?', text)
            if not match:
                await update.message.reply_text("❌ Формат: описание сумма дата,напоминание (дней). Пример: Аренда 30000 2026-06-01,3", reply_markup=keyboards.get_main_keyboard())
                return
            desc = match.group(1)
            amount = float(match.group(2))
            due_date = match.group(3)
            remind_days = int(match.group(4)) if match.group(4) else 0
            db.add_payment(user_id, desc, amount, due_date, repeat=False, remind_days=remind_days)
            await update.message.reply_text(f"✅ Платёж «{desc}» запланирован на {due_date}.", reply_markup=keyboards.get_main_keyboard())
            return

        if state == 'set_payment_dates':
            dates = text.split()
            itype = context.user_data.get('plan_type')
            amount = context.user_data.get('plan_amount')
            desc = context.user_data.get('plan_desc')
            for d in dates:
                db.add_payment(user_id, desc, amount, d, repeat=True)
            await update.message.reply_text("Платежи запланированы. Желаете настроить напоминания?", reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Да", callback_data="set_reminders")],
                [InlineKeyboardButton("Нет", callback_data="cancel_reminders")]
            ]))
            return

        if state == 'remind_days':
            try:
                days = int(text)
                cursor = db.conn.cursor()
                cursor.execute("UPDATE payments SET remind_days=? WHERE user_id=? AND repeat=1 AND remind_days=0", (days, user_id))
                db.conn.commit()
                await update.message.reply_text(f"Напоминания установлены за {days} дн.", reply_markup=keyboards.get_main_keyboard())
            except:
                await update.message.reply_text("Ошибка. Введите число.")
            return

        await update.message.reply_text("🙃 Кажется, я что-то потерял. Давайте начнём сначала.", reply_markup=keyboards.get_main_keyboard())
        return

    # ================= Обычный диалог с ИИ =================
    await handle_ai_dialog(update, context, text)