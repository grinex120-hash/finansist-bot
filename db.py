def get_financial_snapshot(user_id):
    """Возвращает словарь со всеми ключевыми финансовыми данными пользователя."""
    profile = get_user_profile(user_id)
    if not profile:
        return None

    today = datetime.now()
    inc_sum, inc_list = get_month_income_entries(user_id)
    exp_sum, exp_list = get_month_transactions_summary(user_id)

    plan_income = sum(amt for _, amt, _ in get_regular_items(user_id, 'income'))
    plan_expense = sum(amt for _, amt, _ in get_regular_items(user_id, 'expense'))

    balance_now, _ = get_latest_balance(user_id)

    debts = get_debts(user_id)
    total_debt_payment = sum(d[5] for d in debts if d[5])
    total_debt_paid = sum(amt for amt, cat, desc in exp_list if cat == "кредиты/долги")

    goals = get_goals(user_id)
    total_goal_plan = sum(g[5] for g in goals if g[5])
    total_goal_fact = sum(amt for amt, cat, desc in exp_list if cat == "накопления")

    remaining_expenses = max(0, plan_expense + total_debt_payment + total_goal_plan - exp_sum - total_debt_paid - total_goal_fact)
    free_balance = balance_now - remaining_expenses
    remaining_income = max(0, plan_income - inc_sum)
    forecast = free_balance + remaining_income

    # Индикатор здоровья (цвет)
    health_color = "🟢"
    if free_balance < 0:
        health_color = "🔴"
    elif free_balance / (inc_sum if inc_sum > 0 else 1) < 0.05:
        health_color = "🟡"

    # Предупреждения
    warnings = []
    month = today.strftime('%Y-%m')
    for cat in ["еда","транспорт","жильё","здоровье","развлечения","одежда","связь","кредиты/долги","накопления","другое"]:
        lim = check_category_limit(user_id, cat, month)
        if lim:
            spent = get_current_spending_by_category(user_id, cat, month)
            if spent >= lim:
                warnings.append(f"🚨 Превышен лимит по «{cat}»: {spent:.0f}/{lim:.0f} ₽")
            elif spent >= lim * 0.8:
                warnings.append(f"🔸 80% лимита по «{cat}»: {spent:.0f}/{lim:.0f} ₽")
    cursor.execute("SELECT description, amount, due_date FROM payments WHERE user_id=? AND due_date>=? AND paid=0 ORDER BY due_date LIMIT 1",
                   (user_id, today.strftime('%Y-%m-%d')))
    payment = cursor.fetchone()
    if payment:
        days_left = (datetime.strptime(payment[2], "%Y-%m-%d") - today).days
        if days_left <= 3:
            warnings.append(f"🔔 Скоро платёж: {payment[0]} – {payment[1]:.0f} ₽ (через {days_left} дн.)")

    # Полоса прогресса цели
    goal_bar = ""
    if goals:
        goal = goals[0]
        total = goal[2] if goal[2] else 1
        current = min(goal[3], total)
        percent = int(current / total * 100)
        filled = int(percent / 10)
        empty = 10 - filled
        bar = "█" * filled + "░" * empty
        goal_bar = f"🎯 {goal[1]}: {bar} {percent}% ({current:.0f}/{total:.0f} ₽)"

    # Динамика за неделю
    week_ago = (today - timedelta(days=7)).strftime('%Y-%m-%d')
    two_weeks_ago = (today - timedelta(days=14)).strftime('%Y-%m-%d')
    cursor.execute("SELECT SUM(amount) FROM transactions WHERE user_id=? AND date BETWEEN ? AND ?",
                   (user_id, week_ago, today.strftime('%Y-%m-%d')))
    week_spent = cursor.fetchone()[0] or 0
    cursor.execute("SELECT SUM(amount) FROM transactions WHERE user_id=? AND date BETWEEN ? AND ?",
                   (user_id, two_weeks_ago, week_ago))
    prev_week_spent = cursor.fetchone()[0] or 0
    if prev_week_spent > 0:
        change = (week_spent - prev_week_spent) / prev_week_spent * 100
        trend = f"📊 Расходы за неделю: {week_spent:.0f} ₽ ({'+' if change>0 else '-'}{abs(change):.0f}% к прошлой неделе)"
    else:
        trend = ""

    # ========== НОВЫЕ МЕТРИКИ ==========
    # 1. Средние расходы за 3 месяца (для подушки)
    three_months_ago = (today - timedelta(days=90)).strftime('%Y-%m-%d')
    cursor.execute("SELECT SUM(amount) FROM transactions WHERE user_id=? AND date BETWEEN ? AND ?",
                   (user_id, three_months_ago, today.strftime('%Y-%m-%d')))
    total_3m_exp = cursor.fetchone()[0] or 0
    avg_monthly_expense = total_3m_exp / 3  # среднее за 3 месяца

    cushion_target = avg_monthly_expense * 3  # рекомендуемая подушка (3 месяца расходов)
    # Ищем цель с ключевым словом "подушка"
    cushion_current = 0
    for g in goals:
        if "подушк" in g[1].lower() or "финансов" in g[1].lower():
            cushion_current = g[3]  # current_saved
            break
    cushion_percent = (cushion_current / cushion_target * 100) if cushion_target > 0 else 0

    # 2. Норма сбережения
    if inc_sum > 0:
        savings_rate = (inc_sum - exp_sum) / inc_sum * 100
        if savings_rate < 0:
            savings_rate = 0
    else:
        savings_rate = 0

    # 3. Долговая нагрузка
    debt_monthly_total = sum(d[5] for d in debts)  # сумма monthly_payment
    if inc_sum > 0:
        debt_load = (debt_monthly_total / inc_sum * 100)
        if debt_load > 100:
            debt_load = 100
    else:
        debt_load = 0
    # цветовой индикатор
    if debt_load < 30:
        debt_emoji = "🟢"
    elif debt_load < 50:
        debt_emoji = "🟡"
    else:
        debt_emoji = "🔴"

    return {
        "date": today,
        "inc_sum": inc_sum,
        "exp_sum": exp_sum,
        "plan_income": plan_income,
        "plan_expense": plan_expense,
        "balance_now": balance_now,
        "free_balance": free_balance,
        "forecast": forecast,
        "health_color": health_color,
        "warnings": warnings,
        "goal_bar": goal_bar,
        "trend": trend,
        "total_debt_paid": total_debt_paid,
        "total_debt_payment": total_debt_payment,
        "total_goal_fact": total_goal_fact,
        "total_goal_plan": total_goal_plan,
        "inc_list": inc_list,
        "exp_list": exp_list,
        "reg_incomes": get_regular_items(user_id, 'income'),
        "reg_expenses": get_regular_items(user_id, 'expense'),
        "goals": goals,
        "debts": debts,
        "settings": get_user_settings(user_id),
        # новые поля
        "cushion_current": cushion_current,
        "cushion_target": cushion_target,
        "cushion_percent": cushion_percent,
        "savings_rate": savings_rate,
        "debt_load": debt_load,
        "debt_emoji": debt_emoji,
    }