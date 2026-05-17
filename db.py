import sqlite3
import re
import threading
from datetime import datetime, timedelta

conn = sqlite3.connect("finance.db", check_same_thread=False)
cursor = conn.cursor()
conn_lock = threading.Lock()

ALLOWED_USER_SETTINGS_KEYS = {'timezone', 'currency', 'evening_reminder', 'weekly_reminder', 'first_name'}
ALLOWED_GOAL_KEYS = {'description', 'target_amount', 'current_saved', 'deadline', 'monthly_payment'}
ALLOWED_DEBT_KEYS = {'name', 'total_amount', 'rate', 'term', 'monthly_payment', 'current_balance'}
ALLOWED_PAYMENT_KEYS = {'description', 'amount', 'due_date', 'paid', 'repeat', 'remind_days'}

def init_db():
    cursor.executescript("""
        CREATE TABLE IF NOT EXISTS user_finances (
            user_id INTEGER PRIMARY KEY,
            monthly_income REAL DEFAULT 0,
            monthly_fixed_expenses REAL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS income_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount REAL,
            description TEXT,
            date DATE DEFAULT (date('now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount REAL,
            category TEXT,
            description TEXT,
            date DATE DEFAULT (date('now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS regular_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            type TEXT,
            amount REAL,
            description TEXT
        );
        CREATE TABLE IF NOT EXISTS daily_balance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            balance REAL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS goals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            description TEXT,
            target_amount REAL DEFAULT 0,
            current_saved REAL DEFAULT 0,
            deadline TEXT,
            monthly_payment REAL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS debts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            name TEXT,
            total_amount REAL DEFAULT 0,
            rate REAL DEFAULT 0,
            term INTEGER DEFAULT 0,
            monthly_payment REAL DEFAULT 0,
            current_balance REAL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS challenges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            name TEXT,
            type TEXT,
            target_amount REAL,
            category TEXT,
            start_date TEXT,
            end_date TEXT,
            current_progress REAL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            description TEXT,
            amount REAL,
            due_date TEXT,
            paid INTEGER DEFAULT 0,
            repeat INTEGER DEFAULT 1,
            remind_days INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS user_settings (
            user_id INTEGER PRIMARY KEY,
            timezone TEXT DEFAULT 'Europe/Moscow',
            currency TEXT DEFAULT '₽',
            evening_reminder INTEGER DEFAULT 1,
            weekly_reminder INTEGER DEFAULT 1,
            first_name TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS category_limits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            category TEXT,
            limit_amount REAL,
            month TEXT
        );
    """)
    conn.commit()
    try:
        cursor.execute("ALTER TABLE user_settings ADD COLUMN first_name TEXT DEFAULT ''")
        conn.commit()
    except:
        pass
    try:
        cursor.execute("ALTER TABLE goals ADD COLUMN monthly_payment REAL DEFAULT 0")
        conn.commit()
    except:
        pass
    try:
        cursor.execute("ALTER TABLE debts ADD COLUMN term INTEGER DEFAULT 0")
        conn.commit()
    except:
        pass

# ---------- Основные функции ----------
def get_user_profile(user_id):
    with conn_lock:
        cursor.execute("SELECT monthly_income, monthly_fixed_expenses FROM user_finances WHERE user_id=?", (user_id,))
        row = cursor.fetchone()
    if row:
        return {"income": row[0], "expenses": row[1]}
    return None

def ensure_profile(user_id):
    with conn_lock:
        cursor.execute("INSERT OR IGNORE INTO user_finances (user_id, monthly_income, monthly_fixed_expenses) VALUES (?, 0, 0)", (user_id,))
        conn.commit()

def update_monthly_income_from_entries(user_id):
    now = datetime.now()
    month_start = now.strftime('%Y-%m') + '-01'
    if now.month == 12:
        next_month = now.replace(year=now.year+1, month=1, day=1)
    else:
        next_month = now.replace(month=now.month+1, day=1)
    month_end = (next_month - timedelta(days=1)).strftime('%Y-%m-%d')
    with conn_lock:
        cursor.execute("SELECT SUM(amount) FROM income_entries WHERE user_id=? AND date BETWEEN ? AND ?",
                       (user_id, month_start, month_end))
        total = cursor.fetchone()[0] or 0
        ensure_profile(user_id)
        cursor.execute("UPDATE user_finances SET monthly_income=? WHERE user_id=?", (total, user_id))
        conn.commit()

def add_income_entry(user_id, amount, description):
    with conn_lock:
        cursor.execute("INSERT INTO income_entries (user_id, amount, description) VALUES (?, ?, ?)", (user_id, amount, description))
        conn.commit()
    update_monthly_income_from_entries(user_id)
    balance_now, _ = get_latest_balance(user_id)
    new_balance = balance_now + amount
    record_balance(user_id, new_balance, update_balance=False)

def add_expense_transaction(user_id, amount, description, category=None):
    if category is None:
        category = 'другое'
    with conn_lock:
        cursor.execute("INSERT INTO transactions (user_id, amount, category, description) VALUES (?, ?, ?, ?)",
                       (user_id, amount, category, description))
        conn.commit()
    balance_now, _ = get_latest_balance(user_id)
    new_balance = balance_now - amount
    record_balance(user_id, new_balance, update_balance=False)

def get_month_income_entries(user_id):
    now = datetime.now()
    month_start = now.strftime('%Y-%m') + '-01'
    if now.month == 12:
        next_month = now.replace(year=now.year+1, month=1, day=1)
    else:
        next_month = now.replace(month=now.month+1, day=1)
    month_end = (next_month - timedelta(days=1)).strftime('%Y-%m-%d')
    with conn_lock:
        cursor.execute("SELECT amount, description FROM income_entries WHERE user_id=? AND date BETWEEN ? AND ?",
                       (user_id, month_start, month_end))
        rows = cursor.fetchall()
    total = sum(r[0] for r in rows)
    return total, rows

def get_month_transactions_summary(user_id):
    now = datetime.now()
    month_start = now.strftime('%Y-%m') + '-01'
    if now.month == 12:
        next_month = now.replace(year=now.year+1, month=1, day=1)
    else:
        next_month = now.replace(month=now.month+1, day=1)
    month_end = (next_month - timedelta(days=1)).strftime('%Y-%m-%d')
    with conn_lock:
        cursor.execute("SELECT amount, category, description FROM transactions WHERE user_id=? AND date BETWEEN ? AND ?",
                       (user_id, month_start, month_end))
        rows = cursor.fetchall()
    total = sum(r[0] for r in rows)
    return total, rows

def get_latest_balance(user_id):
    with conn_lock:
        cursor.execute("SELECT balance, timestamp FROM daily_balance WHERE user_id=? ORDER BY timestamp DESC LIMIT 1", (user_id,))
        row = cursor.fetchone()
    return (row[0], row[1]) if row else (0, None)

def record_balance(user_id, new_balance, description=None, update_balance=True):
    with conn_lock:
        cursor.execute("INSERT INTO daily_balance (user_id, balance) VALUES (?, ?)", (user_id, new_balance))
        conn.commit()
    return 0  # упрощённо, чтобы избежать рекурсии

def get_regular_items(user_id, item_type):
    with conn_lock:
        cursor.execute("SELECT id, amount, description FROM regular_items WHERE user_id=? AND type=?", (user_id, item_type))
        return cursor.fetchall()

def add_regular_item(user_id, item_type, amount, description):
    with conn_lock:
        cursor.execute("INSERT INTO regular_items (user_id, type, amount, description) VALUES (?, ?, ?, ?)",
                       (user_id, item_type, amount, description))
        conn.commit()

def delete_regular_item(item_id):
    with conn_lock:
        cursor.execute("DELETE FROM regular_items WHERE id=?", (item_id,))
        conn.commit()

def get_active_challenges(user_id):
    today = datetime.now().strftime("%Y-%m-%d")
    with conn_lock:
        cursor.execute("SELECT id, name, type, target_amount, category, start_date, end_date, current_progress FROM challenges WHERE user_id=? AND end_date >= ?",
                       (user_id, today))
        return cursor.fetchall()

def update_challenge_progress(challenge_id, amount):
    with conn_lock:
        cursor.execute("UPDATE challenges SET current_progress = current_progress + ? WHERE id=?", (amount, challenge_id))
        conn.commit()
        cursor.execute("SELECT current_progress, target_amount, name FROM challenges WHERE id=?", (challenge_id,))
        return cursor.fetchone()

def check_category_limit(user_id, category, month):
    with conn_lock:
        cursor.execute("SELECT limit_amount FROM category_limits WHERE user_id=? AND category=? AND month=?",
                       (user_id, category, month))
        row = cursor.fetchone()
    return row[0] if row else None

def get_current_spending_by_category(user_id, category, month):
    with conn_lock:
        cursor.execute("SELECT SUM(amount) FROM transactions WHERE user_id=? AND category=? AND date BETWEEN date(?) AND date(?)",
                       (user_id, category, f"{month}-01", f"{month}-31"))
        row = cursor.fetchone()
    return row[0] if row[0] else 0

def set_category_limit(user_id, category, limit_amount, month):
    with conn_lock:
        cursor.execute("INSERT INTO category_limits (user_id, category, limit_amount, month) VALUES (?, ?, ?, ?)",
                       (user_id, category, limit_amount, month))
        conn.commit()

def get_user_settings(user_id):
    with conn_lock:
        cursor.execute("SELECT timezone, currency, evening_reminder, weekly_reminder, first_name FROM user_settings WHERE user_id=?", (user_id,))
        row = cursor.fetchone()
    if row:
        return {"timezone": row[0], "currency": row[1], "evening_reminder": bool(row[2]), "weekly_reminder": bool(row[3]), "first_name": row[4]}
    else:
        with conn_lock:
            cursor.execute("INSERT OR IGNORE INTO user_settings (user_id) VALUES (?)", (user_id,))
            conn.commit()
        return {"timezone": "Europe/Moscow", "currency": "₽", "evening_reminder": True, "weekly_reminder": True, "first_name": ""}

def update_user_setting(user_id, key, value):
    if key not in ALLOWED_USER_SETTINGS_KEYS:
        raise ValueError(f"Invalid setting key: {key}")
    with conn_lock:
        cursor.execute(f"UPDATE user_settings SET {key}=? WHERE user_id=?", (value, user_id))
        conn.commit()

def save_user_profile(user_id, income=None, expenses=None):
    ensure_profile(user_id)
    with conn_lock:
        if income is not None:
            cursor.execute("UPDATE user_finances SET monthly_income=? WHERE user_id=?", (income, user_id))
        if expenses is not None:
            cursor.execute("UPDATE user_finances SET monthly_fixed_expenses=? WHERE user_id=?", (expenses, user_id))
        conn.commit()

def create_challenge(user_id, name, ctype, target, category, end_date):
    start = datetime.now().strftime("%Y-%m-%d")
    with conn_lock:
        cursor.execute("INSERT INTO challenges (user_id, name, type, target_amount, category, start_date, end_date) VALUES (?, ?, ?, ?, ?, ?, ?)",
                       (user_id, name, ctype, target, category, start, end_date))
        conn.commit()

def add_goal(user_id, description, target_amount=0, deadline=None, monthly_payment=0):
    if target_amount == 0 or deadline is None:
        nums = re.findall(r'\d+', description)
        if nums and target_amount == 0:
            target_amount = float(nums[0])
        term_match = re.search(r'за\s+(\d+)\s*(?:месяц|мес|month)', description)
        if term_match and deadline is None:
            deadline = term_match.group(0)
            months = int(term_match.group(1))
        else:
            months = None
    else:
        months = None
        if deadline:
            term_match = re.search(r'(\d+)\s*(?:месяц|мес|month)', deadline)
            if term_match:
                months = int(term_match.group(1))
    if monthly_payment == 0 and target_amount > 0 and months:
        monthly_payment = target_amount / months
    with conn_lock:
        cursor.execute("INSERT INTO goals (user_id, description, target_amount, deadline, monthly_payment) VALUES (?, ?, ?, ?, ?)",
                       (user_id, description, target_amount, deadline, monthly_payment))
        conn.commit()
    return cursor.lastrowid

def get_goals(user_id):
    with conn_lock:
        cursor.execute("SELECT id, description, target_amount, current_saved, deadline, monthly_payment FROM goals WHERE user_id=?", (user_id,))
        return cursor.fetchall()

def update_goal(goal_id, **kwargs):
    for key, value in kwargs.items():
        if key not in ALLOWED_GOAL_KEYS:
            raise ValueError(f"Invalid goal key: {key}")
        with conn_lock:
            cursor.execute(f"UPDATE goals SET {key}=? WHERE id=?", (value, goal_id))
        conn.commit()

def delete_goal(goal_id):
    with conn_lock:
        cursor.execute("DELETE FROM goals WHERE id=?", (goal_id,))
        conn.commit()

def find_goal_by_keyword(user_id, keyword):
    with conn_lock:
        cursor.execute("SELECT id, description FROM goals WHERE user_id=? AND description LIKE ?", (user_id, f"%{keyword}%"))
        return cursor.fetchone()

def increase_goal_saved(goal_id, amount):
    with conn_lock:
        cursor.execute("UPDATE goals SET current_saved = current_saved + ? WHERE id=?", (amount, goal_id))
        conn.commit()

def parse_debt_input(text: str):
    text = text.strip()
    for word in ['месяц', 'месяцев', 'мес', 'под', 'на']:
        text = re.sub(r'\b' + word + r'\b', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\s+', ' ', text).strip()
    numbers = re.findall(r'\d+\.?\d*', text)
    name = text
    for num in numbers:
        name = name.replace(num, '', 1)
    name = ' '.join(name.split())
    if not name:
        name = numbers[0] if numbers else 'Долг'
    total = float(numbers[0]) if len(numbers) > 0 else 0.0
    rate = float(numbers[1]) if len(numbers) > 1 else 0.0
    term = int(float(numbers[2])) if len(numbers) > 2 else 0
    manual_payment = float(numbers[3]) if len(numbers) > 3 else 0.0
    return name, total, rate, term, manual_payment

def add_debt(user_id, name, total_amount=0, rate=0, term=0, monthly_payment=0, current_balance=None):
    if current_balance is None:
        current_balance = total_amount
    if monthly_payment == 0 and rate > 0 and term > 0:
        r = rate / 100 / 12
        if r == 0:
            monthly_payment = total_amount / term
        else:
            monthly_payment = total_amount * r * (1 + r)**term / ((1 + r)**term - 1)
    elif monthly_payment == 0 and rate > 0 and term == 0:
        monthly_payment = round(total_amount * rate / 1200, 2)
    with conn_lock:
        cursor.execute("INSERT INTO debts (user_id, name, total_amount, rate, term, monthly_payment, current_balance) VALUES (?, ?, ?, ?, ?, ?, ?)",
                       (user_id, name, total_amount, rate, term, monthly_payment, current_balance))
        conn.commit()
    return cursor.lastrowid

def get_debts(user_id):
    with conn_lock:
        cursor.execute("SELECT id, name, total_amount, rate, term, monthly_payment, current_balance FROM debts WHERE user_id=?", (user_id,))
        return cursor.fetchall()

def update_debt(debt_id, **kwargs):
    for key, value in kwargs.items():
        if key not in ALLOWED_DEBT_KEYS:
            raise ValueError(f"Invalid debt key: {key}")
        with conn_lock:
            cursor.execute(f"UPDATE debts SET {key}=? WHERE id=?", (value, debt_id))
        conn.commit()

def delete_debt(debt_id):
    with conn_lock:
        cursor.execute("DELETE FROM debts WHERE id=?", (debt_id,))
        conn.commit()

def find_debt_by_keyword(user_id, keyword):
    with conn_lock:
        cursor.execute("SELECT id, name FROM debts WHERE user_id=? AND name LIKE ?", (user_id, f"%{keyword}%"))
        return cursor.fetchone()

def decrease_debt_balance(debt_id, amount):
    with conn_lock:
        cursor.execute("UPDATE debts SET current_balance = current_balance - ? WHERE id=?", (amount, debt_id))
        conn.commit()

def add_payment(user_id, description, amount, due_date, repeat=True, remind_days=0):
    with conn_lock:
        cursor.execute("INSERT INTO payments (user_id, description, amount, due_date, repeat, remind_days) VALUES (?, ?, ?, ?, ?, ?)",
                       (user_id, description, amount, due_date, repeat, remind_days))
        conn.commit()
    return cursor.lastrowid

def get_payments(user_id, include_paid=False):
    with conn_lock:
        if include_paid:
            cursor.execute("SELECT id, description, amount, due_date, paid, repeat, remind_days FROM payments WHERE user_id=? ORDER BY due_date", (user_id,))
        else:
            cursor.execute("SELECT id, description, amount, due_date, paid, repeat, remind_days FROM payments WHERE user_id=? AND paid=0 ORDER BY due_date", (user_id,))
        return cursor.fetchall()

def update_payment(payment_id, **kwargs):
    for key, value in kwargs.items():
        if key not in ALLOWED_PAYMENT_KEYS:
            raise ValueError(f"Invalid payment key: {key}")
        with conn_lock:
            cursor.execute(f"UPDATE payments SET {key}=? WHERE id=?", (value, payment_id))
        conn.commit()

def delete_payment(payment_id):
    with conn_lock:
        cursor.execute("DELETE FROM payments WHERE id=?", (payment_id,))
        conn.commit()

def get_transactions_for_export(user_id, year_month=None):
    if year_month is None:
        year_month = datetime.now().strftime('%Y-%m')
    start_date = f"{year_month}-01"
    year, month = map(int, year_month.split('-'))
    if month == 12:
        end_date = f"{year+1}-01-01"
    else:
        end_date = f"{year}-{month+1}-01"
    with conn_lock:
        cursor.execute("""
            SELECT date, amount, description, NULL as category FROM income_entries
            WHERE user_id=? AND date BETWEEN ? AND ?
            UNION ALL
            SELECT date, -amount, description, category FROM transactions
            WHERE user_id=? AND date BETWEEN ? AND ?
            ORDER BY date
        """, (user_id, start_date, end_date, user_id, start_date, end_date))
        rows = cursor.fetchall()
    return [{"date": r[0], "amount": r[1], "description": r[2], "category": r[3]} for r in rows]

def get_financial_snapshot(user_id):
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

    health_color = "🟢"
    if free_balance < 0:
        health_color = "🔴"
    elif free_balance / (inc_sum if inc_sum > 0 else 1) < 0.05:
        health_color = "🟡"

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

    # Подушка безопасности
    three_months_ago = (today - timedelta(days=90)).strftime('%Y-%m-%d')
    cursor.execute("SELECT SUM(amount) FROM transactions WHERE user_id=? AND date BETWEEN ? AND ?",
                   (user_id, three_months_ago, today.strftime('%Y-%m-%d')))
    total_3m_exp = cursor.fetchone()[0] or 0
    avg_monthly_expense = total_3m_exp / 3 if total_3m_exp else 0
    cushion_target = avg_monthly_expense * 3
    cushion_current = 0
    for g in goals:
        if "подушк" in g[1].lower() or "финансов" in g[1].lower():
            cushion_current = g[3]
            break
    cushion_percent = (cushion_current / cushion_target * 100) if cushion_target > 0 else 0

    # Норма сбережения
    if inc_sum > 0:
        savings_rate = (inc_sum - exp_sum) / inc_sum * 100
        if savings_rate < 0:
            savings_rate = 0
    else:
        savings_rate = 0

    # Долговая нагрузка
    debt_monthly_total = sum(d[5] for d in debts)
    if inc_sum > 0:
        debt_load = (debt_monthly_total / inc_sum * 100)
        if debt_load > 100:
            debt_load = 100
    else:
        debt_load = 0
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
        "cushion_current": cushion_current,
        "cushion_target": cushion_target,
        "cushion_percent": cushion_percent,
        "savings_rate": savings_rate,
        "debt_load": debt_load,
        "debt_emoji": debt_emoji,
    }