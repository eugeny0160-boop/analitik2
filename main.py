import asyncio
import threading
from datetime import datetime, timedelta
from supabase import create_client
from telegram.ext import Application, MessageHandler, filters
from telegram import Update
import os
from flask import Flask

# === Настройки ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
SOURCE_CHANNEL_ID = int(os.getenv("SOURCE_CHANNEL_ID")) # ID приватного канала
TARGET_CHANNEL_ID = int(os.getenv("TARGET_CHANNEL_ID")) # ID публичного канала
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
PORT = int(os.getenv("PORT", 10000))

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def is_duplicate(url):
    try:
        resp = supabase.table("ingested_content_items").select("id").eq("source_url", url).execute()
        return len(resp.data) > 0
    except:
        return False

def save_post(title, content, url, pub_date):
    if is_duplicate(url): return
    try:
        supabase.table("ingested_content_items").insert({
            "source_url": url,
            "title": title[:500],
            "content": content[:10000],
            "pub_date": pub_date.isoformat(),
            "channel_id": SOURCE_CHANNEL_ID,
            "language": "ru",
            "is_analyzed": False
        }).execute()
        print(f"📥 Сохранён пост: {url}")
    except Exception as e:
        print(f"❌ Ошибка сохранения: {e}")

def generate_report():
    yesterday = datetime.utcnow() - timedelta(days=1)
    try:
        resp = supabase.table("ingested_content_items") \
            .select("*") \
            .gte("pub_date", yesterday.isoformat()) \
            .eq("is_analyzed", False) \
            .order("pub_date", desc=True) \
            .execute()
        posts = resp.data
        if not posts: return "Нет новых данных за последние 24 часа."

        report = [
            f"📊 Аналитический отчёт ({len(posts)} постов)",
            f"Сформирован: {datetime.utcnow().strftime('%d.%m.%Y %H:%M')} UTC",
            "",
            "📌 Последние посты:"
        ]
        for p in posts:
            report.append(f"• {p['content'] or 'Без текста'} [{p['source_url']}]")
        return "\n".join(report)[:2000]
    except Exception as e:
        return f"❌ Ошибка: {e}"

async def send_report(app):
    try:
        report = generate_report()
        await app.bot.send_message(chat_id=TARGET_CHANNEL_ID, text=report)
        print("✅ Отчёт отправлен")

        # Отмечаем как проанализированные
        supabase.table("ingested_content_items") \
            .update({"is_analyzed": True}) \
            .gte("pub_date", (datetime.utcnow() - timedelta(days=1)).isoformat()) \
            .eq("is_analyzed", False) \
            .execute()
    except Exception as e:
        print(f"❌ Ошибка отправки: {e}")

# Обработчик для КАНАЛЬНЫХ постов (channel_post)
async def handle_channel_post(update: Update, context):
    post = update.channel_post
    if post is None: return  # Защита от None

    if post.chat.id != SOURCE_CHANNEL_ID: return

    url = post.link or f"https://t.me/c/{post.chat.id}/{post.message_id}"
    save_post(post.text[:100], post.text, url, post.date)

# === Flask для порта ===
flask_app = Flask(__name__)
@flask_app.route("/") 
def home(): return "Bot is alive", 200

def run_flask():
    flask_app.run(host="0.0.0.0", port=PORT, debug=False)

# === Запуск ===
def main():
    # Запускаем Flask в фоне
    thread = threading.Thread(target=run_flask)
    thread.daemon = True
    thread.start()

    # Запускаем бота
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    # Добавляем обработчик для channel_post
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_channel_post))
    
    print("🚀 Бот запущен...")
    # Отправляем отчёт сразу
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(send_report(app))
    
    # Запускаем polling
    app.run_polling()

if __name__ == "__main__":
    main()
