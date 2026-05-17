from telegram import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup

def get_main_keyboard():
    return ReplyKeyboardMarkup([
        [KeyboardButton("👤 Профиль"), KeyboardButton("📚 Знания")],
        [KeyboardButton("🔧 Инструменты"), KeyboardButton("❓ Помощь")],
    ], resize_keyboard=True)

def get_profile_inline_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📅 Планирование", callback_data="planning_menu")],
        [InlineKeyboardButton("✏️ Редактировать", callback_data="edit_profile")],
        [InlineKeyboardButton("🚨 Лимиты", callback_data="limits_menu")],
        [InlineKeyboardButton("🏠 Назад", callback_data="go_home")],
    ])