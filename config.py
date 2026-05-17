import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GIGACHAT_KEY = os.getenv("GIGACHAT_KEY")

if not TELEGRAM_TOKEN or not GIGACHAT_KEY:
    raise ValueError("Missing TELEGRAM_TOKEN or GIGACHAT_KEY in .env file")