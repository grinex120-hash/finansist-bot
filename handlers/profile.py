from datetime import datetime
import db
import keyboards

def get_profile_text(user_id: int):
    snap = db.get_financial_snapshot(user_id)
    if not snap:
        return "Профиль пуст.", keyboards.get_profile_inline_keyboard()

    lines = [
        f"👤 **Личный кабинет**\n📅 {snap['date'].strftime('%B %Y')}\n",
        f"💰 Доход за месяц:       {snap['inc_sum']:.0f} / {snap['plan_income']:.0f} ₽",
    ]
    for amt, desc in snap['inc_list']:
        lines.append(f"  • {desc}: {amt:.0f} ₽")

    lines.append(f"\n💸 Расходы за месяц:     {snap['exp_sum']:.0f} / {snap['plan_expense']:.0f} ₽")
    for amt, cat, desc in snap['exp_list']:
        lines.append(f"  • {desc}: {amt:.0f} ₽ ({cat})")

    lines.append(f"\n💵 Текущий баланс:       {snap['balance_now']:.0f} ₽")
    lines.append(f"💎 Свободный остаток:    {snap['free_balance']:.0f} ₽")
    lines.append(f"🔮 Прогноз на конец мес: {snap['forecast']:.0f} ₽")
    lines.append(f"🏦 Выплаты по долгам:    {snap['total_debt_paid']:.0f} / {snap['total_debt_payment']:.0f} ₽")
    lines.append(f"🎯 Накопления на цели:   {snap['total_goal_fact']:.0f} / {snap['total_goal_plan']:.0f} ₽")

    if snap['goal_bar']:
        lines.append(snap['goal_bar'])
    if snap['trend']:
        lines.append(snap['trend'])

    # ---- Новые метрики финансовой грамотности ----
    if snap['cushion_target'] > 0:
        lines.append(f"🛡️ Подушка безопасности: {snap['cushion_current']:.0f} / {snap['cushion_target']:.0f} ₽ ({snap['cushion_percent']:.0f}%)")
    else:
        lines.append("🛡️ Подушка безопасности: нет данных (добавьте расходы за 3 месяца)")

    lines.append(f"📈 Норма сбережения: {snap['savings_rate']:.1f}%")

    if snap['debt_load'] > 0:
        lines.append(f"{snap['debt_emoji']} Долговая нагрузка: {snap['debt_load']:.1f}%")
    else:
        lines.append(f"🟢 Долговая нагрузка: 0%")
    # ---------------------------------------------

    if snap['reg_incomes'] or snap['reg_expenses']:
        lines.append("\n📅 Плановые регулярные:")
        for _, amt, desc in snap['reg_incomes']:
            lines.append(f"  + {desc}: {amt:.0f} ₽")
        for _, amt, desc in snap['reg_expenses']:
            lines.append(f"  - {desc}: {amt:.0f} ₽")

    if snap['goals']:
        lines.append("\n🎯 **Цели:**")
        for g in snap['goals']:
            plan_str = f" / {g[5]:.0f} ₽/мес" if g[5] else ""
            lines.append(f"  • {g[1]}: {g[3]:.0f} из {g[2]:.0f} ₽{plan_str}")

    if snap['debts']:
        lines.append("\n🏦 **Долги:**")
        for d in snap['debts']:
            paid = d[2] - d[6]
            lines.append(f"  • {d[1]}: выплачено {paid:.0f} из {d[2]:.0f} ₽ ({d[3]}%)")

    if snap['warnings']:
        lines.append("\n⚠️ **Предупреждения:**")
        lines.extend(f"  {w}" for w in snap['warnings'][:3])

    text = "\n".join(lines)
    keyboard = keyboards.get_profile_inline_keyboard()
    return text, keyboard