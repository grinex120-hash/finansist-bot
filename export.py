import csv
import io
from datetime import datetime
import db

def export_transactions_csv(user_id, year_month=None):
    """Генерирует CSV-строку с транзакциями за месяц."""
    transactions = db.get_transactions_for_export(user_id, year_month)
    if not transactions:
        return None

    output = io.StringIO()
    writer = csv.writer(output, delimiter=';')
    writer.writerow(["Дата", "Сумма", "Описание", "Категория"])
    for t in transactions:
        writer.writerow([t["date"], f"{t['amount']:.2f}", t["description"], t["category"] or ""])
    return output.getvalue()