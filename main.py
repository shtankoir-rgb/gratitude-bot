import os
import sqlite3
import logging
import threading
import asyncio
from datetime import datetime, timedelta
from flask import Flask
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    filters, ContextTypes, ConversationHandler
)

logging.basicConfig(level=logging.INFO)
ASK_NAME, ASK_TEXT, EXPORT_CHOICE = range(3)

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

ADMIN_ID = 389322406

flask_app = Flask(__name__)

@flask_app.route("/")
def index():
    return "Bot is alive"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    flask_app.run(host="0.0.0.0", port=port)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = ReplyKeyboardMarkup(
        [[KeyboardButton("🖌️ Надiслати вдячнiсть"), KeyboardButton("📦 Експорт подяк")]],
        resize_keyboard=True
    )
    await update.message.reply_text(
        "👋 Привiт! Обери дiю нижче або скористайся командами:", reply_markup=keyboard
    )

async def thanks_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Кому хочеш подякувати?")
    return ASK_NAME

async def ask_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["to_whom"] = update.message.text.strip()
    await update.message.reply_text("💬 За що саме? (можна з емодзi, не стримуй себе!)")
    return ASK_TEXT

async def save_thanks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    to_whom = context.user_data.get("to_whom")
    date = datetime.now().strftime("%Y-%m-%d")

    banned_inputs = [
        "📦 експорт подяк", "🖌️ надіслати вдячність",
        "📦", "🖌️", "🥰", "❤️", "💌", "😊", "😉", "👍"
    ]

    if (
        not text
        or len(text) < 5
        or text.lower() in banned_inputs
        or all(char in "❤️🥰📦🖌️💌😊😉👍" for char in text.replace(" ", ""))
    ):
        await update.message.reply_text(
            "⚠️ Напиши, будь ласка, справжню подяку — хоча б кiлька слiв 💌"
        )
        return ASK_TEXT

    c.execute("INSERT INTO thanks (to_whom, text, date) VALUES (?, ?, ?)", (to_whom, text, date))
    conn.commit()

    keyboard = ReplyKeyboardMarkup(
        [[KeyboardButton("🖌️ Ще одну"), KeyboardButton("❌ Завершити")]],
        resize_keyboard=True,
        one_time_keyboard=True
    )

    await update.message.reply_text(
        "❤️ Збережено! Добро шириться ✨\n\nХочеш надіслати ще одну подяку?",
        reply_markup=keyboard
    )

    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = ReplyKeyboardMarkup(
        [[KeyboardButton("🖌️ Надiслати вдячнiсть"), KeyboardButton("📦 Експорт подяк")]],
        resize_keyboard=True
    )
    await update.message.reply_text(
        "✅ Гаразд, збережено! Повертаємося до головного меню 👌",
        reply_markup=keyboard
    )
    return ConversationHandler.END

async def export_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("🚫 Лише адмiн може експортувати подяки.")
        return ConversationHandler.END

    keyboard = ReplyKeyboardMarkup([["7 днiв", "14 днiв"]], one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text("📦 За який перiод витягнути вдячностi?", reply_markup=keyboard)
    return EXPORT_CHOICE

async def export_choose(update: Update, context: ContextTypes.DEFAULT_TYPE):
    days = 7 if "7" in update.message.text else 14
    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

    old_limit = (datetime.now() - timedelta(days=20)).strftime("%Y-%m-%d")
    c.execute("DELETE FROM thanks WHERE date < ?", (old_limit,))
    conn.commit()

    c.execute("SELECT to_whom, text, date FROM thanks WHERE date >= ? ORDER BY to_whom, date", (since,))
    rows = c.fetchall()

    if not rows:
        await update.message.reply_text("🤷‍♀️ Немає подяк за обраний перiод...")
        return ConversationHandler.END

    grouped = {}
    for to_whom, text, date in rows:
        grouped.setdefault(to_whom, []).append((date, text))

    messages = []
    for person, entries in grouped.items():
        block = [f"👤 *{person}*:"] + [f"📅 {d}\n💌 {t}" for d, t in entries]
        messages.append("\n\n".join(block))

    full_text = "\n\n".join(messages)
    chunks = [full_text[i:i+4000] for i in range(0, len(full_text), 4000)]
    for chunk in chunks:
        await update.message.reply_text(chunk, parse_mode="Markdown")

    return ConversationHandler.END

async def clean(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == ADMIN_ID:
        c.execute("DELETE FROM thanks")
        conn.commit()
        await update.message.reply_text("🪑 Усi вдячностi очищено!")
    else:
        await update.message.reply_text("🚫 Лише адмiн може чистити базу!")

async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text.strip().lower()

    if txt in ["🙌 надiслати вдячнiсть", "🙌 ще одну"]:
        return await thanks_entry(update, context)

    elif txt == "📦 експорт подяк":
        return await export_entry(update, context)

def main():
    threading.Thread(target=run_flask).start()

    TOKEN = os.getenv("BOT_TOKEN")
    app = ApplicationBuilder().token(TOKEN).build()

    conv_thanks = ConversationHandler(
        entry_points=[
            CommandHandler("thanks", thanks_entry),
            MessageHandler(filters.Regex("🙌"), thanks_entry)
        ],
        states={
            ASK_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_text)],
            ASK_TEXT: [
                MessageHandler(filters.TEXT & filters.Regex("❌ Завершити"), cancel),
                MessageHandler(filters.TEXT & ~filters.COMMAND, save_thanks)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    conv_export = ConversationHandler(
        entry_points=[
            CommandHandler("export", export_entry),
            MessageHandler(filters.Regex("📦"), export_entry)
        ],
        states={
            EXPORT_CHOICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, export_choose)]
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv_thanks)
    app.add_handler(conv_export)
    app.add_handler(CommandHandler("clean", clean))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_buttons))

    asyncio.run(app.run_polling())

if __name__ == "__main__":
    main()
