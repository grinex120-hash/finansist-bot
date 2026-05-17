import time
from telegram import Update
from telegram.ext import ContextTypes
import db
import utils
import knowledge
import keyboards
import prompts

async def handle_ai_dialog(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    user_id = update.effective_user.id

    # Кэш снэпшота на 30 секунд
    cache_key = f"snapshot_{user_id}"
    snapshot_cache = context.user_data.get(cache_key)
    if snapshot_cache and (time.time() - snapshot_cache['timestamp']) < 30:
        snap = snapshot_cache['data']
    else:
        snap = db.get_financial_snapshot(user_id)
        if snap:
            context.user_data[cache_key] = {'data': snap, 'timestamp': time.time()}

    if not snap:
        await update.message.reply_text("👋 Чтобы я мог давать советы, сначала добавьте хотя бы один доход или расход.", reply_markup=keyboards.get_main_keyboard())
        return

    # Формируем контекст из снэпшота
    ctx_parts = [
        f"💰 Текущий доход за месяц: {snap['inc_sum']:.0f} ₽",
        f"💸 Текущие расходы за месяц: {snap['exp_sum']:.0f} ₽"
    ]
    if snap['reg_incomes']:
        ctx_parts.append("📅 Плановые регулярные доходы: " + ", ".join([f"{desc} {amt:.0f} ₽" for _, amt, desc in snap['reg_incomes']]))
    if snap['reg_expenses']:
        ctx_parts.append("📅 Плановые регулярные расходы: " + ", ".join([f"{desc} {amt:.0f} ₽" for _, amt, desc in snap['reg_expenses']]))
    if snap['inc_list']:
        inc_lines = [f"  {desc}: {amt:.0f} ₽" for amt, desc in snap['inc_list'][:5]]
        ctx_parts.append("🟢 Последние доходы:\n" + "\n".join(inc_lines))
    if snap['exp_list']:
        exp_lines = [f"  {desc}: {amt:.0f} ₽ ({cat})" for amt, cat, desc in snap['exp_list'][:5]]
        ctx_parts.append("🔴 Последние расходы:\n" + "\n".join(exp_lines))
    ctx_parts.append(f"💵 Текущий баланс: {snap['balance_now']:.0f} ₽")
    if snap['goals']:
        goal_lines = ["🎯 Цели:"]
        for g in snap['goals']:
            target_str = f" / {g[2]:.0f} ₽" if g[2] else ""
            dl = f" до {g[4]}" if g[4] else ""
            goal_lines.append(f"  • {g[1]}: {g[3]:.0f}{target_str}{dl}")
        ctx_parts.append("\n".join(goal_lines))
    if snap['debts']:
        debt_lines = ["🏦 Долги:"]
        for d in snap['debts']:
            debt_lines.append(f"  • {d[1]}: {d[2]:.0f} ₽ ({d[3]}%) – ежемес. {d[5]:.0f} ₽, осталось {d[6]:.0f} ₽")
        ctx_parts.append("\n".join(debt_lines))

    # Лимиты (можно добавить в снэпшот, пока берём из БД)
    month = snap['date'].strftime('%Y-%m')
    limit_lines = []
    for cat in ["еда","транспорт","жильё","здоровье","развлечения","одежда","связь","кредиты/долги","накопления","другое"]:
        lim = db.check_category_limit(user_id, cat, month)
        if lim:
            spent = db.get_current_spending_by_category(user_id, cat, month)
            limit_lines.append(f"{cat}: {spent:.0f}/{lim:.0f} ₽")
    if limit_lines:
        ctx_parts.append("🚦 Лимиты:\n" + "\n".join(limit_lines))

    challenges = db.get_active_challenges(user_id)
    if challenges:
        ch_lines = ["🏆 Активные челленджи:"]
        for c in challenges:
            if c[2] == 'save_money':
                ch_lines.append(f"  {c[1]}: {c[7]:.0f}/{c[3]:.0f} ₽")
            else:
                ch_lines.append(f"  {c[1]}: воздержание от {c[4]}")
        ctx_parts.append("\n".join(ch_lines))

    financial_context = "\n".join(ctx_parts)

    # Поиск в базе знаний
    knowledge_context = ""
    keywords = ["долг", "бюджет", "копить", "инвести", "процент", "финанс", "кредит", "сбереж", "накоп"]
    if any(kw in text.lower() for kw in keywords):
        matches = knowledge.search_knowledge(text)
        if matches:
            chunks = "\n\n".join([f"- {doc}\n(источник: {meta['source']})" for doc, meta in matches])
            knowledge_context = f"\n\n📚 Материалы из базы знаний (используй их в ответе):\n{chunks}"

    first_name = snap['settings'].get('first_name', '')
    system_msg = prompts.SYSTEM_FINANCIAL_ASSISTANT.format(first_name=first_name if first_name else 'друг', financial_context=financial_context)
    if knowledge_context:
        system_msg += knowledge_context

    # rate limiting через utils.check_rate_limit
    if not utils.check_rate_limit(user_id):
        await update.message.reply_text("⏳ Вы слишком часто задаёте вопросы. Подождите немного.", reply_markup=keyboards.get_main_keyboard())
        return

    messages = [{"role": "system", "content": system_msg}, {"role": "user", "content": text}]
    try:
        resp = utils.giga_client.chat.completions.create(
            model="GigaChat-Max",
            messages=messages,
            temperature=0.7,
            max_tokens=800,
        )
        reply = resp.choices[0].message.content
    except:
        try:
            resp = utils.giga_client.chat(system_msg + "\n\nВопрос: " + text)
            reply = resp.choices[0].message.content
        except:
            reply = "Ой, что-то пошло не так. Попробуйте ещё раз."

    await update.message.reply_text(reply, reply_markup=keyboards.get_main_keyboard())