import re
import json
import time
from collections import defaultdict
from gigachat import GigaChat
from config import GIGACHAT_KEY
import prompts

giga_client = GigaChat(credentials=GIGACHAT_KEY, verify_ssl_certs=False)

rate_limit_store = defaultdict(list)  # user_id -> list of timestamps

def check_rate_limit(user_id, max_requests=5, period_seconds=60):
    now = time.time()
    timestamps = rate_limit_store[user_id]
    while timestamps and timestamps[0] < now - period_seconds:
        timestamps.pop(0)
    if len(timestamps) >= max_requests:
        return False
    timestamps.append(now)
    return True

def categorize_expense(description: str) -> str:
    prompt = prompts.CATEGORIZE_PROMPT.format(description=description)
    try:
        resp = giga_client.chat(prompt)
        cat = resp.choices[0].message.content.strip().lower()
        valid = ["еда", "транспорт", "жильё", "здоровье", "развлечения", "одежда", "связь", "кредиты/долги", "накопления", "другое"]
        return cat if cat in valid else "другое"
    except:
        return "другое"

def parse_debts(debts_text: str):
    prompt = prompts.DEBT_PARSE_PROMPT.format(text=debts_text)
    try:
        resp = giga_client.chat(prompt)
        raw = resp.choices[0].message.content
        json_match = re.search(r'\[.*\]', raw, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
        else:
            return []
    except:
        return []