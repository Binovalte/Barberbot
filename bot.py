import sqlite3
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

TOKEN = "8666575017:AAEey_XYk6190NSrtOmF8McfGZg8k9lHlEA"
ADMIN_ID = 1144050379 

# ================= DATABASE =================

conn = sqlite3.connect("barber.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    user_id INTEGER,
    number INTEGER
)
""")
conn.commit()

# ================= FUNCTIONS =================

def get_queue():
    cursor.execute("SELECT * FROM queue ORDER BY id")
    return cursor.fetchall()

def add_client(name, user_id):
    cursor.execute("SELECT * FROM queue WHERE user_id=?", (user_id,))
    if cursor.fetchone():
        return None  # already reserved

    cursor.execute("SELECT COUNT(*) FROM queue")
    count = cursor.fetchone()[0]
    number = count + 1

    cursor.execute("INSERT INTO queue (name, user_id, number) VALUES (?, ?, ?)",
                   (name, user_id, number))
    conn.commit()
    return number

def remove_first():
    cursor.execute("SELECT * FROM queue ORDER BY id LIMIT 1")
    first = cursor.fetchone()
    if first:
        cursor.execute("DELETE FROM queue WHERE id=?", (first[0],))
        conn.commit()
    return first

def reset_queue():
    cursor.execute("DELETE FROM queue")
    conn.commit()

# ================= BOT HANDLERS =================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("💈 Reserve", callback_data="reserve")],
    ]

    if update.effective_user.id == ADMIN_ID:
        keyboard.append([InlineKeyboardButton("🛠 Admin Panel", callback_data="admin")])

    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "Welcome to the Barber Shop 💈\nPress reserve to take a number.",
        reply_markup=reply_markup
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "reserve":
        await query.message.reply_text("Please send your name:")
        context.user_data["waiting_name"] = True

    elif query.data == "admin" and query.from_user.id == ADMIN_ID:
        keyboard = [
            [InlineKeyboardButton("▶ Start Next", callback_data="next")],
            [InlineKeyboardButton("📋 Show Queue", callback_data="show")],
            [InlineKeyboardButton("🔄 Reset Queue", callback_data="reset")]
        ]
        await query.message.reply_text("Admin Panel:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data == "next" and query.from_user.id == ADMIN_ID:
        first = remove_first()

        if not first:
            await query.message.reply_text("Queue is empty.")
            return

        queue = get_queue()

        # Notify all
        for person in queue:
            await context.bot.send_message(
                chat_id=person[2],
                text=f"💈 Now shaving number {first[3]}"
            )

        # Notify next client privately
        if queue:
            await context.bot.send_message(
                chat_id=queue[0][2],
                text="🚶 It's your turn. Please come."
            )

        await query.message.reply_text(f"Started number {first[3]}")

    elif query.data == "show" and query.from_user.id == ADMIN_ID:
        queue = get_queue()
        if not queue:
            await query.message.reply_text("Queue empty.")
            return

        text = "📋 Current Queue:\n"
        for q in queue:
            text += f"{q[3]} - {q[1]}\n"

        await query.message.reply_text(text)

    elif query.data == "reset" and query.from_user.id == ADMIN_ID:
        reset_queue()
        await query.message.reply_text("Queue reset successfully.")

async def name_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("waiting_name"):
        name = update.message.text
        number = add_client(name, update.effective_user.id)

        if number is None:
            await update.message.reply_text("⚠ You already have a reservation.")
        else:
            await update.message.reply_text(f"✅ Your number is: {number}")

            # Notify admin
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"New client: {name} - Number {number}"
            )

        context.user_data["waiting_name"] = False

# ================= RUN =================

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CallbackQueryHandler(button_handler))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, name_handler))

app.run_polling()
