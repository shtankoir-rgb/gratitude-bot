import sqlite3
import logging
from datetime import datetime, timedelta
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)

# --- Logging ---
logging.basicConfig(level=logging.INFO)

# --- Conversation states ---
ASK_NAME, ASK_TEXT, EXPORT_CHOOSE = range(3)

# --- Admin ID ---
ADMIN_ID = 389322406

# --- Database setup ---
conn = sqlite3.connect("gratitude.db", check_same_thread=False)
c = conn.cursor()
c.execute("""
CREATE TABLE IF NOT EXISTS thanks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    to_whom TEXT,
    text TEXT,
    date TEXT
)
""")
conn.commit()

# --- Static stickers ---
STICKERS = {
    "start": "CAACAgIAAxkBAAEF3R1mZLhQzBlMRzZjcB6CI4Zm0bYJxAACVgADVp29CpgZyZ-5OePVNQQ",
    "thanks_saved": "CAACAgIAAxkBAAEF3R9mZLhqu_2cR2E7ciZyTndsoMQS_QACsA0AAladvQoJ1ndUZa8w-TEE",
    "export_ready": "CAACAgIAAxkBAAEF3SBmZLiD6DnLHGKKOgIQOYzGDqTewAACqw0AAladvQqn5mLo0U25DjEE"
}

# --- Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[
        KeyboardButton("📝 Написати вдячність"),
        KeyboardButton("📦 Отримати вдячності")
    ]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(
        "👋 Привіт, легендо! Обери, що хочеш зробити:", reply_markup=reply_markup
    )
    await context.bot.send_sticker(chat_id=update.effective_chat.id, sticker=STICKERS["start"])

async def thanks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🙋‍♀️ Кому хочеш подякувати?")
    return ASK_NAME

async def ask_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["to_whom"] = update.message.text.strip()
    await update.message.reply_text("💬 За що саме? (можна з емодзі, не стримуй себе!)")
    return ASK_TEXT

async def save_thanks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    to_whom = context.user_data.get("to_whom")
    date = datetime.now().strftime("%Y-%m-%d")
    c.execute("INSERT INTO thanks (to_whom, text, date) VALUES (?, ?, ?)", (to_whom, text, date))
    conn.commit()
    await update.message.reply_text("🔥 Збережено! Тепер світ трішки кращий ❤️")
    await context.bot.send_sticker(chat_id=update.effective_chat.id, sticker=STICKERS["thanks_saved"])
    return ConversationHandler.END

async def export(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = ReplyKeyboardMarkup([["7 днів", "14 днів"]], one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text("📦 За який період витягнути вдячності?", reply_markup=keyboard)
    return EXPORT_CHOOSE

async def export_choose(update: Update, context: ContextTypes.DEFAULT_TYPE):
    days = 7 if "7" in update.message.text else 14
    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

    # Видаляємо вдячності старші за 20 днів
    old_limit = (datetime.now() - timedelta(days=20)).strftime("%Y-%m-%d")
    c.execute("DELETE FROM thanks WHERE date < ?", (old_limit,))
    conn.commit()

    c.execute("SELECT to_whom, text, date FROM thanks WHERE date >= ? ORDER BY to_whom, date", (since,))
    rows = c.fetchall()

    if not rows:
        await update.message.reply_text("🤷‍♂️ Немає вдячностей за обраний період... Можеш це виправити 😉")
        return ConversationHandler.END

    grouped = {}
    for to_whom, text, date in rows:
        grouped.setdefault(to_whom, []).append((date, text))

    messages = []
    for person, entries in grouped.items():
        block = [f"👤 *{person}*: "] + [f"📅 {d}\n💌 {t}" for d, t in entries]
        messages.append("\n\n".join(block))

    full_text = "\n\n".join(messages)
    chunks = [full_text[i:i+4000] for i in range(0, len(full_text), 4000)]
    for chunk in chunks:
        await update.message.reply_text(chunk, parse_mode="Markdown")

    await context.bot.send_sticker(chat_id=update.effective_chat.id, sticker=STICKERS["export_ready"])
    return ConversationHandler.END

async def clean(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("⛔️ Тільки адмін може чистити базу! ❤️")
        return
    c.execute("DELETE FROM thanks")
    conn.commit()
    await update.message.reply_text("🧹 Базу очищено повністю! 🔥")

async def button_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "📝 Написати вдячність":
        return await thanks(update, context)
    elif text == "📦 Отримати вдячності":
        return await export(update, context)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Скасовано. Але ми завжди раді твоїм добрим словам 🙌")
    return ConversationHandler.END

# --- Main ---
def main():
    import os
    TOKEN = os.getenv("BOT_TOKEN")
    app = ApplicationBuilder().token(TOKEN).build()

    conv_thanks = ConversationHandler(
        entry_points=[CommandHandler("thanks", thanks), MessageHandler(filters.Regex("^📝 Написати вдячність$"), thanks)],
        states={
            ASK_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_text)],
            ASK_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_thanks)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    conv_export = ConversationHandler(
        entry_points=[CommandHandler("export", export), MessageHandler(filters.Regex("^📦 Отримати вдячності$"), export)],
        states={
            EXPORT_CHOOSE: [MessageHandler(filters.TEXT & ~filters.COMMAND, export_choose)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("clean", clean))
    app.add_handler(conv_thanks)
    app.add_handler(conv_export)
    app.add_handler(MessageHandler(filters.Regex("^(📝 Написати вдячність|📦 Отримати вдячності)$"), button_router))
    app.run_polling()

if __name__ == "__main__":
    main()
