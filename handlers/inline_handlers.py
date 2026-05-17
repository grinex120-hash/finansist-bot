from datetime import datetime
from collections import defaultdict
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
import db
from .profile import get_profile_text
from summary import get_main_summary   # <--- исправлено: абсолютный импорт
import utils
import charts
import keyboards
import prompts
import io
import export

# Вспомогательные функции подменю
async def show_goals_menu(query, user_id):
    goals = db.get_goals(user_id)
    text = "🎯 **Ваши цели:**\n"
    if goals:
        for g in goals:
            target_str = f" / {g[2]:.0f} ₽" if g[2] else ""
            dl = f" до {g[4]}" if g[4] else ""
            text += f"• {g[1]}: {g[3]:.0f}{target_str}{dl}\n"
    else:
        text += "Пока целей нет.\n"
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Добавить цель", callback_data="add_goal"),
         InlineKeyboardButton("🗑 Удалить", callback_data="delete_goal_menu")],
        [InlineKeyboardButton("🔙 Назад", callback_data="edit_profile")]
    ])
    await query.edit_message_text(text, reply_markup=kb)

async def show_debts_menu(query, user_id):
    debts = db.get_debts(user_id)
    text = "🏦 **Ваши долги:**\n"
    if debts:
        for d in debts:
            text += f"• {d[1]}: {d[2]:.0f} ₽ ({d[3]}%) – ежемес. {d[5]:.0f} ₽, осталось {d[6]:.0f} ₽\n"
    else:
        text += "Долгов нет – отлично!\n"
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Добавить долг", callback_data="add_debt"),
         InlineKeyboardButton("🗑 Удалить", callback_data="delete_debt_menu")],
        [InlineKeyboardButton("🔙 Назад", callback_data="edit_profile")]
    ])
    await query.edit_message_text(text, reply_markup=kb)

async def show_limits_menu(query, user_id):
    month = datetime.now().strftime('%Y-%m')
    text = "🚦 **Текущие лимиты на месяц:**\n"
    limits_exist = False
    for cat in ["еда","транспорт","жильё","здоровье","развлечения","одежда","связь","кредиты/долги","накопления","другое"]:
        lim = db.check_category_limit(user_id, cat, month)
        if lim:
            spent = db.get_current_spending_by_category(user_id, cat, month)
            text += f"• {cat}: {spent:.0f}/{lim:.0f} ₽\n"
            limits_exist = True
    if not limits_exist:
        text += "Лимиты не установлены.\n"
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🚨 Установить лимит", callback_data="set_limit_tool")],
        [InlineKeyboardButton("🔙 Назад", callback_data="refresh_profile")]
    ])
    await query.edit_message_text(text, reply_markup=kb)

async def show_review(query, user_id):
    now = datetime.now()
    plan_income = sum(amt for _, amt, _ in db.get_regular_items(user_id, 'income'))
    plan_expense = sum(amt for _, amt, _ in db.get_regular_items(user_id, 'expense'))
    inc_fact, _ = db.get_month_income_entries(user_id)
    exp_fact, _ = db.get_month_transactions_summary(user_id)
    msg = (
        f"📈 Обзор за {now.strftime('%m.%Y')}\n"
        f"💰 Доходы: план {plan_income:.0f} / факт {inc_fact:.0f} ₽\n"
        f"💸 Расходы: план {plan_expense:.0f} / факт {exp_fact:.0f} ₽\n"
        "Хотите обновить регулярные статьи на основе фактических данных?"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Обновить регулярные", callback_data="update_regular")],
        [InlineKeyboardButton("❌ Отмена", callback_data="cancel_review")],
    ])
    await query.edit_message_text(msg, reply_markup=kb)

async def update_regular_now(user_id, query):
    for item_id, _, _ in db.get_regular_items(user_id, 'income'):
        db.delete_regular_item(item_id)
    for item_id, _, _ in db.get_regular_items(user_id, 'expense'):
        db.delete_regular_item(item_id)
    inc_sum, _ = db.get_month_income_entries(user_id)
    if inc_sum > 0:
        db.add_regular_item(user_id, 'income', inc_sum, "Факт дохода")
    exp_by_cat = defaultdict(float)
    _, exp_list = db.get_month_transactions_summary(user_id)
    for amt, cat, desc in exp_list:
        exp_by_cat[cat] += amt
    for cat, total in exp_by_cat.items():
        if total > 0:
            db.add_regular_item(user_id, 'expense', total, cat.capitalize())
    await query.edit_message_text("Регулярные статьи обновлены на основе фактических данных.")

async def financial_analysis(query, user_id):
    await query.edit_message_text("⏳ Провожу глубокий анализ ваших финансов...")
    profile = db.get_user_profile(user_id)
    if not profile:
        await query.edit_message_text("Нет данных.")
        return
    income = profile["income"]
    expenses = profile["expenses"]
    ctx_parts = [
        f"💰 Текущий доход за месяц: {income:.0f} ₽",
        f"💸 Текущие расходы за месяц: {expenses:.0f} ₽"
    ]
    reg_incomes = db.get_regular_items(user_id, 'income')
    reg_expenses = db.get_regular_items(user_id, 'expense')
    if reg_incomes:
        ctx_parts.append("📅 Плановые регулярные доходы: " + ", ".join([f"{desc} {amt:.0f} ₽" for _, amt, desc in reg_incomes]))
    if reg_expenses:
        ctx_parts.append("📅 Плановые регулярные расходы: " + ", ".join([f"{desc} {amt:.0f} ₽" for _, amt, desc in reg_expenses]))
    cursor = db.conn.cursor()
    cursor.execute("SELECT amount, description, date FROM income_entries WHERE user_id=? ORDER BY date DESC LIMIT 5", (user_id,))
    last_incomes = cursor.fetchall()
    if last_incomes:
        inc_lines = [f"  {desc}: {amt:.0f} ₽ ({date})" for amt, desc, date in last_incomes]
        ctx_parts.append("🟢 Последние доходы:\n" + "\n".join(inc_lines))
    cursor.execute("SELECT amount, category, description, date FROM transactions WHERE user_id=? ORDER BY date DESC LIMIT 10", (user_id,))
    last_expenses = cursor.fetchall()
    if last_expenses:
        exp_lines = [f"  {desc}: {amt:.0f} ₽ ({cat}) ({date})" for amt, cat, desc, date in last_expenses]
        ctx_parts.append("🔴 Последние 10 расходов:\n" + "\n".join(exp_lines))
    balance_now, _ = db.get_latest_balance(user_id)
    if balance_now:
        ctx_parts.append(f"💵 Текущий баланс (на руках): {balance_now:.0f} ₽")
    goals = db.get_goals(user_id)
    if goals:
        goal_lines = ["🎯 Цели:"]
        for g in goals:
            target_str = f" / {g[2]:.0f} ₽" if g[2] else ""
            dl = f" до {g[4]}" if g[4] else ""
            goal_lines.append(f"  • {g[1]}: {g[3]:.0f}{target_str}{dl}")
        ctx_parts.append("\n".join(goal_lines))
    debts = db.get_debts(user_id)
    if debts:
        debt_lines = ["🏦 Долги:"]
        for d in debts:
            debt_lines.append(f"  • {d[1]}: {d[2]:.0f} ₽ ({d[3]}%) – ежемес. {d[5]:.0f} ₽, осталось {d[6]:.0f} ₽")
        ctx_parts.append("\n".join(debt_lines))
    financial_context = "\n".join(ctx_parts)

    system_msg = prompts.FINANCIAL_ANALYSIS_SYSTEM.format(financial_context=financial_context)

    try:
        resp = utils.giga_client.chat(system_msg)
        reply = resp.choices[0].message.content
    except:
        reply = "Ошибка анализа."
    await query.edit_message_text(reply[:4000])

# ---------- главный обработчик ----------
async def inline_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    # --- Планирование ---
    if data == "planning_menu":
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Регулярный доход", callback_data="reg_add_income")],
            [InlineKeyboardButton("➕ Регулярный расход", callback_data="reg_add_expense")],
            [InlineKeyboardButton("📋 Список регулярных", callback_data="reg_list")],
            [InlineKeyboardButton("💳 Запланированные платежи", callback_data="payments_list")],
            [InlineKeyboardButton("➕ Добавить платёж вручную", callback_data="add_payment_manual")],
            [InlineKeyboardButton("🗑 Удалить регулярный", callback_data="reg_del_menu")],
            [InlineKeyboardButton("🗑 Удалить платёж", callback_data="del_payment_menu")],
            [InlineKeyboardButton("🔙 Назад", callback_data="refresh_profile")]
        ])
        await query.edit_message_text("📅 Планирование бюджета и платежей:", reply_markup=keyboard)

    elif data == "add_payment_manual":
        context.user_data['awaiting'] = 'add_payment_manual'
        await query.edit_message_text("Введите описание, сумму и дату (ГГГГ-ММ-ДД) через пробел, а также через запятую напоминание (например, за 3 дня). Пример: Аренда 30000 2026-06-01,3")

    # --- Регулярные ---
    elif data == "reg_add_income":
        context.user_data['awaiting'] = 'regular_income'
        await query.edit_message_text("Введите сумму и описание регулярного дохода (например, `50000 зарплата`):")
    elif data == "reg_add_expense":
        context.user_data['awaiting'] = 'regular_expense'
        await query.edit_message_text("Введите сумму и описание регулярного расхода (например, `15000 аренда`):")
    elif data == "reg_list":
        items = db.get_regular_items(user_id, 'income') + db.get_regular_items(user_id, 'expense')
        if not items:
            await query.edit_message_text("🫧 Пока нет регулярных записей.")
        else:
            text = "📋 **Ваши регулярные статьи:**\n"
            for item_id, amt, desc in items:
                text += f"• {desc}: {amt:.0f} ₽\n"
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🗑 Удалить", callback_data="reg_del_menu")]
            ])
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=keyboard)
    elif data == "reg_del_menu":
        items = db.get_regular_items(user_id, 'income') + db.get_regular_items(user_id, 'expense')
        if not items:
            await query.answer("Нечего удалять.")
            return
        keyboard = []
        for item_id, amt, desc in items:
            keyboard.append([InlineKeyboardButton(f"{desc}: {amt:.0f} ₽", callback_data=f"delreg_{item_id}")])
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="planning_menu")])
        await query.edit_message_text("Выберите запись для удаления:", reply_markup=InlineKeyboardMarkup(keyboard))
    elif data.startswith("delreg_"):
        item_id = int(data.split("_")[1])
        db.delete_regular_item(item_id)
        await query.answer("Удалено!")
        items = db.get_regular_items(user_id, 'income') + db.get_regular_items(user_id, 'expense')
        text = "📋 **Ваши регулярные статьи:**\n" + "\n".join([f"• {desc}: {amt:.0f} ₽" for _, amt, desc in items])
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🗑 Удалить", callback_data="reg_del_menu")]])
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=keyboard)

    # --- Редактирование ---
    elif data == "edit_profile":
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎯 Цели", callback_data="goals_menu"),
             InlineKeyboardButton("🏦 Долги", callback_data="debts_menu")],
            [InlineKeyboardButton("👤 Имя", callback_data="edit_name"),
             InlineKeyboardButton("📎 Экспорт CSV", callback_data="export_csv")],
            [InlineKeyboardButton("🔙 Назад", callback_data="refresh_profile")]
        ])
        await query.edit_message_text("✏️ Что будем редактировать?", reply_markup=keyboard)
    elif data == "edit_name":
        context.user_data['awaiting'] = 'edit_name'
        await query.edit_message_text("📝 Как к вам обращаться? Напишите новое имя.")

    # --- Экспорт CSV ---
    elif data == "export_csv":
        csv_data = export.export_transactions_csv(user_id)
        if csv_data:
            await context.bot.send_document(
                chat_id=user_id,
                document=io.BytesIO(csv_data.encode('utf-8-sig')),
                filename=f"transactions_{datetime.now().strftime('%Y-%m')}.csv",
                caption="📊 Ваши транзакции за текущий месяц"
            )
            await query.answer("CSV отправлен!")
        else:
            await query.answer("Нет данных для экспорта.")

    # --- Цели ---
    elif data == "goals_menu":
        await show_goals_menu(query, user_id)
    elif data == "add_goal":
        context.user_data['awaiting'] = 'add_goal'
        await query.edit_message_text("🎯 Опишите цель: краткое описание, желаемая сумма (необязательно), срок (необязательно). Пример: «Накопить 50000 на отпуск к июню»")
    elif data == "delete_goal_menu":
        goals = db.get_goals(user_id)
        if not goals:
            await query.answer("Нет целей для удаления.")
            return
        keyboard = [[InlineKeyboardButton(f"❌ {g[1]}", callback_data=f"delgoal_{g[0]}")] for g in goals]
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="edit_profile")])
        await query.edit_message_text("Выберите цель для удаления:", reply_markup=InlineKeyboardMarkup(keyboard))
    elif data.startswith("delgoal_"):
        goal_id = int(data.split("_")[1])
        db.delete_goal(goal_id)
        await query.answer("Цель удалена!")
        await show_goals_menu(query, user_id)

    # --- Долги ---
    elif data == "debts_menu":
        await show_debts_menu(query, user_id)
    elif data == "add_debt":
        context.user_data['awaiting'] = 'add_debt'
        await query.edit_message_text(
            "🏦 Введите данные долга: Название Сумма Процент Срок(мес) [Платёж]\n"
            "Пример: Кредит 150000 18 12\n"
            "Или с ручным платежом: Кредит 150000 18 12 15000"
        )
    elif data == "delete_debt_menu":
        debts = db.get_debts(user_id)
        if not debts:
            await query.answer("Нет долгов для удаления.")
            return
        keyboard = [[InlineKeyboardButton(f"❌ {d[1]}", callback_data=f"deldebt_{d[0]}")] for d in debts]
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="edit_profile")])
        await query.edit_message_text("Выберите долг для удаления:", reply_markup=InlineKeyboardMarkup(keyboard))
    elif data.startswith("deldebt_"):
        debt_id = int(data.split("_")[1])
        db.delete_debt(debt_id)
        await query.answer("Долг удалён!")
        await show_debts_menu(query, user_id)

    # --- Лимиты ---
    elif data == "limits_menu":
        await show_limits_menu(query, user_id)
    elif data == "set_limit_tool":
        context.user_data['awaiting'] = 'set_limit'
        await query.edit_message_text("🚨 Введите категорию и сумму лимита (например, `продукты 10000`):")

    # --- Платежи ---
    elif data == "payments_list":
        payments = db.get_payments(user_id)
        if not payments:
            await query.edit_message_text("💳 Платежи не запланированы.")
        else:
            text = "📋 **Запланированные платежи:**\n"
            for pid, desc, amt, due, paid, repeat, remind in payments:
                status = "✅" if paid else "⏳"
                text += f"{status} {desc}: {amt:.0f} ₽ ({due})"
                if repeat:
                    text += " 🔁"
                text += "\n"
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("🗑 Удалить платёж", callback_data="del_payment_menu")],
                [InlineKeyboardButton("🔙 Назад", callback_data="planning_menu")]
            ])
            await query.edit_message_text(text, reply_markup=kb)
    elif data == "del_payment_menu":
        payments = db.get_payments(user_id)
        if not payments:
            await query.answer("Нет платежей для удаления.")
            return
        keyboard = [[InlineKeyboardButton(f"❌ {d[1]} ({d[2]:.0f} ₽)", callback_data=f"delpay_{p[0]}")] for p in payments]
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="planning_menu")])
        await query.edit_message_text("Выберите платёж для удаления:", reply_markup=InlineKeyboardMarkup(keyboard))
    elif data.startswith("delpay_"):
        pid = int(data.split("_")[1])
        db.delete_payment(pid)
        await query.answer("Платёж удалён.")
        payments = db.get_payments(user_id)
        text = "📋 **Запланированные платежи:**\n" if payments else "💳 Платежи не запланированы."
        for p in payments:
            status = "✅" if p[4] else "⏳"
            text += f"{status} {p[1]}: {p[2]:.0f} ₽ ({p[3]})\n"
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🗑 Удалить платёж", callback_data="del_payment_menu")],
            [InlineKeyboardButton("🔙 Назад", callback_data="planning_menu")]
        ])
        await query.edit_message_text(text, reply_markup=kb)

    # --- Инструменты ---
    elif data == "tools":
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎯 Челленджи", callback_data="challenges_menu")],
            [InlineKeyboardButton("📊 График", callback_data="chart")],
            [InlineKeyboardButton("🏦 Кредитный калькулятор", callback_data="loan_calc_tool")],
            [InlineKeyboardButton("📋 Финразбор", callback_data="financial_analysis")],
            [InlineKeyboardButton("🔙 Назад", callback_data="refresh_profile")]
        ])
        await query.edit_message_text("🔧 Инструменты:", reply_markup=keyboard)
    elif data == "challenges_menu":
        challenges = db.get_active_challenges(user_id)
        if challenges:
            ch_list = "\n".join([f"• {c[1]} ({c[2]})" for c in challenges])
            msg = f"🏆 Ваши активные челленджи:\n{ch_list}\n\nХотите создать новый?"
        else:
            msg = "🏆 У вас пока нет активных челленджей. Создадим?"
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Создать челлендж", callback_data="create_challenge")],
            [InlineKeyboardButton("🔙 Назад", callback_data="tools")]
        ])
        await query.edit_message_text(msg, reply_markup=kb)
    elif data == "create_challenge":
        context.user_data['awaiting'] = 'challenge_setup'
        await query.edit_message_text("🎯 Введите данные челленджа: `тип сумма категория дата_окончания`\nПример: `воздержание 0 кофе 2026-06-01`")
    elif data == "loan_calc_tool":
        context.user_data['awaiting'] = 'loan_calc'
        await query.edit_message_text("🏦 Введите данные кредита через пробел: сумма, годовая ставка (%), срок в месяцах.\nПример: `500000 18 36`")
    elif data == "chart":
        url = charts.get_category_chart_url(user_id)
        if url:
            await context.bot.send_photo(chat_id=user_id, photo=url, caption="Расходы по категориям за месяц")
            await query.answer("График готов!")
        else:
            await query.answer("Нет данных для графика.")

    # --- Планирование дат (callback'и) ---
    elif data.startswith("plan_dates_"):
        parts = data.split("_", 4)
        if len(parts) >= 5:
            _, _, itype, amount, desc = parts
            context.user_data['plan_type'] = itype
            context.user_data['plan_amount'] = float(amount)
            context.user_data['plan_desc'] = desc
            await query.edit_message_text("Введите даты платежей через пробел (например, 10 25 для чисел месяца или ГГГГ-ММ-ДД).")
            context.user_data['awaiting'] = 'set_payment_dates'
        else:
            await query.answer("Ошибка параметров.")
    elif data == "cancel_plan":
        await query.edit_message_text("Хорошо, просто регулярная статья.")
    elif data == "set_reminders":
        await query.edit_message_text("За сколько дней до даты напомнить? Введите число (например, 3).")
        context.user_data['awaiting'] = 'remind_days'
    elif data == "cancel_reminders":
        await query.edit_message_text("Напоминания не будут настроены.")

    # --- Прочее ---
    elif data == "show_review":
        await show_review(query, user_id)
    elif data == "update_regular":
        await update_regular_now(user_id, query)
    elif data == "financial_analysis":
        await financial_analysis(query, user_id)
    elif data == "refresh_profile":
        text, keyboard = get_profile_text(user_id)
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=keyboard)
    elif data == "go_home":
        summary = get_main_summary(user_id)
        if summary:
            await context.bot.send_message(chat_id=user_id, text=summary, parse_mode="Markdown", reply_markup=keyboards.get_main_keyboard())
        else:
            await context.bot.send_message(chat_id=user_id, text="🏠 Главный экран", reply_markup=keyboards.get_main_keyboard())
        await query.message.delete()
    elif data == "cancel_review":
        await query.edit_message_text("Обзор отменён.")
    else:
        await query.edit_message_text("🔍 Неизвестная команда.")