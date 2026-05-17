from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime, timedelta
import logging
import db
from summary import get_monthly_report_text

logger = logging.getLogger(__name__)

_scheduler = None

async def check_reminders_and_repeats(app):
    today = datetime.now().strftime("%Y-%m-%d")
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    cursor = db.conn.cursor()

    # 1. Повторяющиеся платежи
    cursor.execute("SELECT id, user_id, description, amount, due_date, repeat, remind_days FROM payments WHERE date(due_date) <= date(?) AND paid=0 AND repeat=1", (today,))
    payments = cursor.fetchall()
    for pid, user_id, desc, amount, due_str, repeat, remind_days in payments:
        old_date = datetime.strptime(due_str, "%Y-%m-%d")
        new_date = old_date + timedelta(days=30)
        db.update_payment(pid, due_date=new_date.strftime("%Y-%m-%d"))

    # 2. Напоминания о завтрашних платежах
    cursor.execute("SELECT user_id, description, amount, due_date, remind_days FROM payments WHERE date(due_date) = date(?) AND paid=0", (tomorrow,))
    upcoming = cursor.fetchall()
    for user_id, desc, amount, due_str, remind_days in upcoming:
        try:
            await app.bot.send_message(user_id, f"🔔 Завтра платёж «{desc}» на {amount:.0f} ₽.")
        except Exception as e:
            logger.error(f"Reminder error: {e}")

    # 3. Напоминания за N дней
    for days in [3, 7, 1]:
        target_date = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
        cursor.execute("SELECT user_id, description, amount, due_date FROM payments WHERE date(due_date) = date(?) AND paid=0 AND remind_days=?", (target_date, days))
        for user_id, desc, amount, due_str in cursor.fetchall():
            try:
                await app.bot.send_message(user_id, f"⏰ Через {days} дн. платёж «{desc}» на {amount:.0f} ₽.")
            except Exception as e:
                logger.error(f"Reminder {days}d error: {e}")

async def weekly_challenge_reminder(app):
    cursor = db.conn.cursor()
    cursor.execute("SELECT user_id, id, name, type, target_amount, category, end_date, current_progress FROM challenges WHERE end_date >= date('now')")
    challenges = cursor.fetchall()
    for user_id, cid, name, ctype, target, category, end_date, progress in challenges:
        days_left = (datetime.strptime(end_date, "%Y-%m-%d") - datetime.now()).days
        if days_left <= 0:
            continue
        if ctype == 'save_money':
            pct = progress / target * 100 if target > 0 else 0
            msg = f"💰 Челлендж «{name}»: {pct:.0f}% ({progress:.0f}/{target:.0f} ₽)"
        else:
            msg = f"🚫 Челлендж «{name}»: воздержание от «{category}»"
        try:
            await app.bot.send_message(user_id, msg)
        except Exception as e:
            logger.error(f"Challenge reminder error: {e}")

async def monthly_report(app):
    """Отправляет каждому пользователю отчёт за прошедший месяц 1-го числа."""
    cursor = db.conn.cursor()
    cursor.execute("SELECT DISTINCT user_id FROM user_finances")
    users = cursor.fetchall()
    for (user_id,) in users:
        try:
            report_text = get_monthly_report_text(user_id)
            if report_text:
                await app.bot.send_message(user_id, report_text, parse_mode="Markdown")
        except Exception as e:
            logger.error(f"Monthly report error for user {user_id}: {e}")

def start_scheduler(app):
    global _scheduler
    _scheduler = BackgroundScheduler(timezone="Europe/Moscow")
    _scheduler.add_job(lambda: app.create_task(check_reminders_and_repeats(app)), CronTrigger(hour=10, minute=0))
    _scheduler.add_job(lambda: app.create_task(weekly_challenge_reminder(app)), CronTrigger(day_of_week='mon', hour=9, minute=0))
    _scheduler.add_job(lambda: app.create_task(monthly_report(app)), CronTrigger(day=1, hour=9, minute=0))
    _scheduler.start()
    return _scheduler

def stop_scheduler():
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None