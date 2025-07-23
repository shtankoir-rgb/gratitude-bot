import sqlite3
import logging
from datetime import datetime, timedelta
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler

# --- Налаштування логування ---
logging.basicConfig(level=logging.INFO)

# --- Стани розмови ---
ASK_NAME, ASK_TEXT = range(2)

# --- Ініціалізація бази даних ---
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

# --- Статичні стикери ---
STICKERS = {
    "start": "CAACAgIAAxkBAAEF45NmZb9QkV9oS1dmdqz8RNEAFuXnbwACAgADwZxgDJUbP-vc5PiDNAQ",
    "thanks_saved": "CAACAgIAAxkBAAEF45VmZcDA5Fu_t2O2q89QDYEXWxzcrAACBgADwZxgDAfVOvMXU85gNAQ",
    "export_ready": "CAACAgIAAxkBAAEF45dmZcDp5uBg2SkPfTSpc8LyXvB3BwACBQADwZxgDAxz_dipbfqGNAQ"
}

# --- /start ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Привіт, легендо! Хочеш зробити день комусь теплішим? Напиши /thanks або /export — і поїхали 🚀")
    await context.bot.send_sticker(chat_id=update.effective_chat.id, sticker=STICKERS["start"])

# --- /thanks ---
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

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Скасовано. Але ми завжди раді твоїм добрим словам 🙌")
    return ConversationHandler.END

# --- /export ---
async def export(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = ReplyKeyboardMarkup([["7 днів", "14 днів"]], one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text("📦 За який період витягнути вдячності?", reply_markup=keyboard)
    return 1

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
        block = [f"👤 *{person}*:"] + [f"📅 {d}\n💌 {t}" for d, t in entries]
        messages.append("\n\n".join(block))

    full_text = "\n\n".join(messages)

    # Розбиваємо текст на частини до 4000 символів
    chunks = [full_text[i:i+4000] for i in range(0, len(full_text), 4000)]
    for chunk in chunks:
        await update.message.reply_text(chunk, parse_mode="Markdown")

    await context.bot.send_sticker(chat_id=update.effective_chat.id, sticker=STICKERS["export_ready"])
    return ConversationHandler.END

# --- Main ---
def main():
    import os
    TOKEN = os.getenv("BOT_TOKEN")
    app = ApplicationBuilder().token(TOKEN).build()

    conv_thanks = ConversationHandler(
        entry_points=[CommandHandler("thanks", thanks)],
        states={
            ASK_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_text)],
            ASK_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_thanks)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    conv_export = ConversationHandler(
        entry_points=[CommandHandler("export", export)],
        states={
            1: [MessageHandler(filters.TEXT & ~filters.COMMAND, export_choose)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv_thanks)
    app.add_handler(conv_export)
    app.run_polling()

if __name__ == "__main__":
    main()
