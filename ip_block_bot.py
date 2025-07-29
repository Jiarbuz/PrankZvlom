import telebot
import re
import os
import time
import json

BOT_TOKEN = "8430330790:AAG1YWeiP2f1GaLP4J6XEQ0FDjk0wlvRWWA"
ADMIN_ID = 6330358945
BLOCK_DURATION_HOURS = 6
BLOCKED_IPS_FILE = "blocked_ips.json"
STATS_FILE = "block_stats.json"

bot = telebot.TeleBot(BOT_TOKEN)
blocked_ips = {}
block_stats = {"total_blocks": 0}

def load_data():
    global blocked_ips, block_stats
    if os.path.exists(BLOCKED_IPS_FILE):
        with open(BLOCKED_IPS_FILE, "r") as f:
            blocked_ips = json.load(f)
    if os.path.exists(STATS_FILE):
        with open(STATS_FILE, "r") as f:
            block_stats = json.load(f)
    auto_cleanup()

def save_data():
    with open(BLOCKED_IPS_FILE, "w") as f:
        json.dump(blocked_ips, f)
    with open(STATS_FILE, "w") as f:
        json.dump(block_stats, f)

def auto_cleanup():
    now = time.time()
    expired = [ip for ip, t in blocked_ips.items() if now - t > BLOCK_DURATION_HOURS * 3600]
    for ip in expired:
        del blocked_ips[ip]

@bot.message_handler(commands=["block"])
def handle_block(message):
    if message.from_user.id != ADMIN_ID:
        return
    parts = message.text.strip().split()
    if len(parts) != 2:
        return bot.reply_to(message, "❗ Используй: `/block 1.2.3.4`", parse_mode="Markdown")
    ip = parts[1]
    if not re.match(r"^\d{1,3}(\.\d{1,3}){3}$", ip):
        return bot.reply_to(message, "⚠️ Неверный IP.")
    blocked_ips[ip] = time.time()
    block_stats["total_blocks"] += 1
    save_data()
    bot.reply_to(message, f"✅ IP `{ip}` заблокирован.", parse_mode="Markdown")

@bot.message_handler(commands=["unblock"])
def handle_unblock(message):
    if message.from_user.id != ADMIN_ID:
        return
    parts = message.text.strip().split()
    if len(parts) != 2:
        return bot.reply_to(message, "❗ Используй: `/unblock 1.2.3.4`", parse_mode="Markdown")
    ip = parts[1]
    if ip in blocked_ips:
        del blocked_ips[ip]
        save_data()
        bot.reply_to(message, f"🟢 IP `{ip}` разблокирован.", parse_mode="Markdown")
    else:
        bot.reply_to(message, f"ℹ️ IP `{ip}` не найден.", parse_mode="Markdown")

@bot.message_handler(commands=["blocked"])
def handle_blocked(message):
    if message.from_user.id != ADMIN_ID:
        return
    auto_cleanup()
    if not blocked_ips:
        return bot.reply_to(message, "📭 Список пуст.")
    now = time.time()
    msg = "🚫 Заблокированные IP:\n\n"
    for ip, timestamp in blocked_ips.items():
        mins = int((now - timestamp) / 60)
        msg += f"• `{ip}` — {mins} мин назад\n"
    bot.reply_to(message, msg, parse_mode="Markdown")

@bot.message_handler(commands=["clear"])
def handle_clear(message):
    if message.from_user.id != ADMIN_ID:
        return
    blocked_ips.clear()
    save_data()
    bot.reply_to(message, "🧹 Список IP очищен.")

@bot.message_handler(commands=["stats"])
def handle_stats(message):
    if message.from_user.id != ADMIN_ID:
        return
    total = block_stats.get("total_blocks", 0)
    count = len(blocked_ips)
    bot.reply_to(message, f"📊 Всего блоков: *{total}*\n🔒 Сейчас заблокировано: *{count}*", parse_mode="Markdown")

load_data()
print("✅ Бот запущен.")
bot.infinity_polling()
