import sqlite3
import time
import asyncio

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ================= CONFIG =================
TOKEN = "8666575017:AAEey_XYk6190NSrtOmF8McfGZg8k9lHlEA"
ADMIN_ID = 1144050379

AVG_TIME = 7 * 60
NEXT_TIMEOUT = 5 * 60

pending_next = {}

# ================= DATABASE =================
conn = sqlite3.connect("barber.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    user_id INTEGER,
    number INTEGER,
    created_at REAL,
    status TEXT DEFAULT 'waiting'
)
""")
conn.commit()

# ================= UI =================

CLIENT_MENU = ReplyKeyboardMarkup(
    [["📋 My status", "❌ Cancel"], ["🔁 Move to end"]],
    resize_keyboard=True
)

ADMIN_MENU = InlineKeyboardMarkup([
    [InlineKeyboardButton("💈 Current", callback_data="current")],
    [InlineKeyboardButton("📣 Notify next", callback_data="notify_next")],
    [InlineKeyboardButton("⏭ Skip", callback_data="skip")],
    [InlineKeyboardButton("▶ Next", callback_data="next")],
    [InlineKeyboardButton("🚨 Alert", callback_data="alert")],
    [InlineKeyboardButton("📋 Show", callback_data="show")],
    [InlineKeyboardButton("🔄 Reset", callback_data="reset")],
])

# ================= HELPERS =================

def get_queue():
    cursor.execute("SELECT * FROM queue ORDER BY id")
    return cursor.fetchall()

def reset_queue():
    cursor.execute("DELETE FROM queue")
    conn.commit()

def remove_first():
    cursor.execute("SELECT * FROM queue ORDER BY id LIMIT 1")
    first = cursor.fetchone()
    if first:
        cursor.execute("DELETE FROM queue WHERE id=?", (first[0],))
        conn.commit()
    return first

def add_client(name, user_id):
    cursor.execute("SELECT * FROM queue WHERE user_id=?", (user_id,))
    if cursor.fetchone():
        return None

    cursor.execute("SELECT COUNT(*) FROM queue")
    number = cursor.fetchone()[0] + 1

    cursor.execute(
        "INSERT INTO queue (name, user_id, number, created_at, status) VALUES (?, ?, ?, ?, 'waiting')",
        (name, user_id, number, time.time()),
    )
    conn.commit()
    return number

def find_user(user_id):
    cursor.execute("SELECT * FROM queue WHERE user_id=?", (user_id,))
    return cursor.fetchone()

# ================= ALERT =================

async def admin_alert(app, text):
    for _ in range(2):
        await app.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"🚨 ALERT\n{text}"
        )
        await asyncio.sleep(1)

# ================= NEXT NOTIFY =================

async def notify_next(app):
    queue = get_queue()

    if len(queue) < 2:
        return

    next_client = queue[1]
    user_id = next_client[2]

    pending_next[user_id] = time.time()

    cursor.execute(
        "UPDATE queue SET status='next' WHERE user_id=?",
        (user_id,)
    )
    conn.commit()

    await app.bot.send_message(
        chat_id=user_id,
        text="🚶 You are NEXT at the barber.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ I am coming", callback_data="coming")],
            [InlineKeyboardButton("❌ Cancel", callback_data="cancel_next")]
        ])
    )

    await app.bot.send_message(
        chat_id=ADMIN_ID,
        text=f"🔔 Next: {next_client[3]} - {next_client[1]}"
    )

# ================= BACKGROUND MONITOR =================

async def monitor(app):
    while True:
        await asyncio.sleep(30)

        now = time.time()

        for user_id, start in list(pending_next.items()):
            elapsed = now - start

            if 120 < elapsed < 150:
                await app.bot.send_message(user_id, "⏳ Reminder: you are NEXT")

            if 240 < elapsed < 270:
                await app.bot.send_message(user_id, "⚠ Final reminder!")

            if elapsed > NEXT_TIMEOUT:
                cursor.execute("DELETE FROM queue WHERE user_id=?", (user_id,))
                conn.commit()

                pending_next.pop(user_id, None)

                queue = get_queue()
                if queue:
                    await app.bot.send_message(queue[0][2], "🚶 You are now NEXT")

# ================= START =================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == ADMIN_ID:
        await update.message.reply_text("🛠 Admin Panel", reply_markup=ADMIN_MENU)
    else:
        await update.message.reply_text(
            "💈 Welcome\nUse /reserve",
            reply_markup=CLIENT_MENU
        )

# ================= RESERVE =================

async def reserve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["waiting_name"] = True
    await update.message.reply_text("✏ Send your name:")

# ================= NAME INPUT =================

async def name_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("waiting_name"):
        await update.message.reply_text("Use buttons 👇", reply_markup=CLIENT_MENU)
        return

    name = update.message.text
    number = add_client(name, update.effective_user.id)

    if number is None:
        await update.message.reply_text("⚠ Already reserved")
        return

    queue = get_queue()
    pos = len(queue) - 1
    eta = pos * AVG_TIME // 60

    context.user_data["waiting_name"] = False

    await update.message.reply_text(
        f"✅ Number: {number}\n⏳ ETA: {eta} min",
        reply_markup=CLIENT_MENU
    )

# ================= CLIENT BUTTONS =================

async def client_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id

    if text == "📋 My status":
        user = find_user(user_id)
        if not user:
            await update.message.reply_text("No reservation.")
            return
        await update.message.reply_text(f"📍 Number {user[3]}")

    elif text == "❌ Cancel":
        cursor.execute("DELETE FROM queue WHERE user_id=?", (user_id,))
        conn.commit()
        await update.message.reply_text("❌ Cancelled")

    elif text == "🔁 Move to end":
        user = find_user(user_id)
        if not user:
            return

        cursor.execute("DELETE FROM queue WHERE user_id=?", (user_id,))
        conn.commit()

        cursor.execute("SELECT COUNT(*) FROM queue")
        number = cursor.fetchone()[0] + 1

        cursor.execute(
            "INSERT INTO queue (name, user_id, number, created_at, status) VALUES (?, ?, ?, ?, 'waiting')",
            (user[1], user_id, number, time.time()),
        )
        conn.commit()

        await update.message.reply_text("🔁 Moved to end")

# ================= CALLBACKS =================

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    data = query.data
    queue = get_queue()

    # ================= ADMIN =================
    if user_id == ADMIN_ID:

        if data == "current":
            if queue:
                c = queue[0]
                await query.message.reply_text(f"💈 Now: {c[3]} - {c[1]}")

        elif data == "notify_next":
            await notify_next(context.application)

        elif data == "skip":
            skipped = remove_first()
            await query.message.reply_text(f"⏭ Skipped {skipped[3] if skipped else 'none'}")
            await notify_next(context.application)

        elif data == "next":
            first = remove_first()
            await query.message.reply_text(f"▶ Next {first[3] if first else 'empty'}")
            await notify_next(context.application)

        elif data == "show":
            text = "📋 Queue:\n"
            for q in queue:
                text += f"{q[3]} - {q[1]}\n"
            await query.message.reply_text(text)

        elif data == "reset":
            reset_queue()
            await query.message.reply_text("Reset done")

        elif data == "alert":
            await admin_alert(context.application, "Manual alert")

    # ================= CLIENT =================
    else:

        if data == "coming":
            pending_next.pop(user_id, None)
            await query.message.reply_text("✅ Confirmed")

        elif data == "cancel_next":
            pending_next.pop(user_id, None)

            cursor.execute("DELETE FROM queue WHERE user_id=?", (user_id,))
            conn.commit()

            queue = get_queue()
            if queue:
                await context.bot.send_message(queue[0][2], "🚶 You are now NEXT")

            await query.message.reply_text("❌ Cancelled")

# ================= POST INIT (FIXED) =================

async def post_init(app):
    app.create_task(monitor(app))

# ================= RUN =================

app = ApplicationBuilder().token(TOKEN).post_init(post_init).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("reserve", reserve))

app.add_handler(CallbackQueryHandler(button_handler))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, client_buttons))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, name_handler))

app.run_polling()
