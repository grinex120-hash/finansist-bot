from datetime import datetime, timedelta
import db

def get_main_summary(user_id: int) -> str:
    snap = db.get_financial_snapshot(user_id)
    if not snap:
        return None

    lines = [
        f"📊 **Сводка за {snap['date'].strftime('%B %Y')}**",
        f"{snap['health_color']} Финансовое здоровье: {snap['health_color']}",
        f"💰 Доход за месяц:       {snap['inc_sum']:.0f} / {snap['plan_income']:.0f} ₽",
        f"💸 Расходы за месяц:     {snap['exp_sum']:.0f} / {snap['plan_expense']:.0f} ₽",
        f"💵 Текущий баланс:       {snap['balance_now']:.0f} ₽",
        f"💎 Свободный остаток:    {snap['free_balance']:.0f} ₽",
        f"🔮 Прогноз на конец мес: {snap['forecast']:.0f} ₽",
        f"🏦 Выплаты по долгам:    {snap['total_debt_paid']:.0f} / {snap['total_debt_payment']:.0f} ₽",
        f"🎯 Накопления на цели:   {snap['total_goal_fact']:.0f} / {snap['total_goal_plan']:.0f} ₽",
    ]

    if snap['goal_bar']:
        lines.append(snap['goal_bar'])
    if snap['trend']:
        lines.append(snap['trend'])
    if snap['warnings']:
        lines.append("\n⚠️ **Предупреждения:**")
        lines.extend(f"  {w}" for w in snap['warnings'])

    # Новые метрики
    if snap['cushion_target'] > 0:
        lines.append(f"🛡️ Подушка безопасности: {snap['cushion_current']:.0f} / {snap['cushion_target']:.0f} ₽ ({snap['cushion_percent']:.0f}%)")
    else:
        lines.append("🛡️ Подушка безопасности: нет данных (добавьте расходы за 3 месяца)")

    lines.append(f"📈 Норма сбережения: {snap['savings_rate']:.1f}%")

    if snap['debt_load'] > 0:
        lines.append(f"{snap['debt_emoji']} Долговая нагрузка: {snap['debt_load']:.1f}%")
    else:
        lines.append(f"🟢 Долговая нагрузка: 0%")

    return "\n".join(lines)

def get_monthly_report_text(user_id: int) -> str:
    """Формирует отчёт за ПРОШЕДШИЙ месяц (для отправки 1-го числа)."""
    today = datetime.now()
    first_day_current = today.replace(day=1)
    last_month_end = first_day_current - timedelta(days=1)
    last_month_start = last_month_end.replace(day=1)

    cursor = db.conn.cursor()
    cursor.execute("SELECT SUM(amount) FROM income_entries WHERE user_id=? AND date BETWEEN ? AND ?",
                   (user_id, last_month_start.strftime('%Y-%m-%d'), last_month_end.strftime('%Y-%m-%d')))
    inc_sum = cursor.fetchone()[0] or 0
    cursor.execute("SELECT SUM(amount), category FROM transactions WHERE user_id=? AND date BETWEEN ? AND ? GROUP BY category",
                   (user_id, last_month_start.strftime('%Y-%m-%d'), last_month_end.strftime('%Y-%m-%d')))
    exp_rows = cursor.fetchall()
    exp_sum = sum(r[0] for r in exp_rows)

    goals = db.get_goals(user_id)
    debts = db.get_debts(user_id)

    prompt = f"На основе данных: доход {inc_sum:.0f} ₽, расход {exp_sum:.0f} ₽, цели: {len(goals)}, долги: {len(debts)}. Дай одну короткую рекомендацию по улучшению финансов (1-2 предложения)."
    try:
        import utils
        resp = utils.giga_client.chat(prompt)
        advice = resp.choices[0].message.content
    except:
        advice = "Продолжайте следить за финансами!"

    lines = [
        f"📅 **Финансовый отчёт за {last_month_start.strftime('%B %Y')}**",
        f"💰 Доходы: {inc_sum:.0f} ₽",
        f"💸 Расходы: {exp_sum:.0f} ₽",
        f"📈 Сбережено: {inc_sum - exp_sum:.0f} ₽",
        "",
        "🏆 **Прогресс целей:**",
    ]
    for g in goals:
        lines.append(f"  • {g[1]}: {g[3]:.0f} из {g[2]:.0f} ₽")
    lines.append("")
    if debts:
        lines.append("🏦 **Долги:**")
        for d in debts:
            paid = d[2] - d[6]
            lines.append(f"  • {d[1]}: выплачено {paid:.0f} из {d[2]:.0f} ₽")
        lines.append("")
    lines.append(f"💡 **Совет:** {advice}")
    lines.append("\n✍️ Чтобы посмотреть детали, откройте профиль: 👤 Профиль")

    return "\n".join(lines)