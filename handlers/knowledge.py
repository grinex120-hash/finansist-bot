from telegram import Update
from telegram.ext import ContextTypes
import knowledge
import utils
import keyboards

async def handle_knowledge_query(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    matches = knowledge.search_knowledge(text)
    if not matches:
        await update.message.reply_text("📚 Ничего не найдено. Попробуйте перефразировать вопрос.", reply_markup=keyboards.get_main_keyboard())
        return

    chunks = "\n\n".join([f"- {doc}\n(источник: {meta['source']})" for doc, meta in matches])
    prompt = f"Ты финансовый советник. Дай развёрнутый ответ на основе:\n{chunks}\n\nВопрос: {text}"
    try:
        resp = utils.giga_client.chat(prompt)
        reply = resp.choices[0].message.content
    except:
        reply = "Ошибка при получении ответа."
    await update.message.reply_text(reply, reply_markup=keyboards.get_main_keyboard())