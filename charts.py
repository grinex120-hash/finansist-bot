import json
from urllib.parse import quote
import db

def get_category_chart_url(user_id):
    total, rows = db.get_month_transactions_summary(user_id)
    if not rows:
        return None
    cats = {}
    for amount, cat, desc in rows:
        cats[cat] = cats.get(cat, 0) + amount
    labels = list(cats.keys())
    data = list(cats.values())
    chart_config = {
        "type": "pie",
        "data": {
            "labels": labels,
            "datasets": [{
                "data": data,
                "backgroundColor": ["#FF6384","#36A2EB","#FFCE56","#4BC0C0","#9966FF","#FF9F40","#C9CBCF"]
            }]
        },
        "options": {
            "title": {"display": True, "text": "Расходы по категориям за месяц"}
        }
    }
    config_json = json.dumps(chart_config)
    return f"https://quickchart.io/chart?c={quote(config_json)}"