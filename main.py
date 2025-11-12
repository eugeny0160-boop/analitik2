import asyncio
import threading
from datetime import datetime, timedelta
from supabase import create_client
from telegram.ext import Application, MessageHandler, filters, ContextTypes
from telegram import Update
import os
from flask import Flask, request # <-- Добавляем Flask

# === ЧТЕНИЕ ПЕРЕМЕННЫХ ИЗ ОКРУЖЕНИЯ (Render) ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
SOURCE_CHANNEL_ID = int(os.getenv("SOURCE_CHANNEL_ID"))  # ID приватного канала
TARGET_CHANNEL_ID = int(os.getenv("TARGET_CHANNEL_ID"))   # ID публичного канала
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
PORT = int(os.getenv("PORT", 10000))  # Порт от Render или 10000 по умолчанию

# === ИНИЦИАЛИЗАЦИЯ ===
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Проверка: был ли этот пост уже обработан?
def is_duplicate(url: str) -> bool:
    try:
        response = supabase.table("ingested_content_items").select("id").eq("source_url", url).execute()
        return len(response.data) > 0
    except Exception as e:
        print(f"❌ Ошибка при проверке дубликата: {e}")
        return False

# Сохранить пост в базу (только если не дубль)
def save_post(title, content, url, pub_date):
    if is_duplicate(url):
        print(f"⚠️ Пропущен дубль: {url}")
        return

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
        print(f"❌ Ошибка при сохранении: {e}")

# Генерация отчёта (только посты за последние 24 часа, непроанализированные)
def generate_daily_report():
    try:
        yesterday = datetime.utcnow() - timedelta(days=1)
        response = supabase.table("ingested_content_items") \
            .select("*") \
            .gte("pub_date", yesterday.isoformat()) \
            .eq("is_analyzed", False) \
            .order("pub_date", desc=True) \
            .execute()

        posts = response.data
        if not posts:
            return "Нет новых данных за последние 24 часа."

        report = [
            f"📊 Аналитический отчёт (постов за 24ч: {len(posts)})",
            f"Сформирован: {datetime.utcnow().strftime('%d.%m.%Y %H:%M')} UTC",
            "",
            "📌 Последние посты:",
        ]

        for post in posts:
            url = post["source_url"]
            content = post["content"] or "Нет текста"
            report.append(f"• {content} [{url}]")

        full_text = "\n".join(report)
        return full_text[:2000]

    except Exception as e:
        return f"❌ Ошибка генерации отчёта: {e}"

# Отправка отчёта
async def send_daily_report_async(app: Application):
    try:
        report = generate_daily_report()
        await app.bot.send_message(chat_id=TARGET_CHANNEL_ID, text=report)
        print(f"✅ Тестовый отчёт отправлен: {datetime.utcnow().strftime('%d.%m.%Y %H:%M')}")

        # Отмечаем все посты за последние 24 часа как проанализированные
        yesterday = datetime.utcnow() - timedelta(days=1)
        supabase.table("ingested_content_items") \
            .update({"is_analyzed": True}) \
            .gte("pub_date", yesterday.isoformat()) \
            .eq("is_analyzed", False) \
            .execute()

    except Exception as e:
        print(f"❌ Ошибка отправки отчёта: {e}")

# Обработка новых постов из Telegram
async def handle_new_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if message.chat.id != SOURCE_CHANNEL_ID:
        return

    text = message.text or ""
    url = message.link or f"https://t.me/c/{message.chat.id}/{message.message_id}"

    save_post(
        title=text[:100],
        content=text,
        url=url,
        pub_date=message.date
    )

# === Flask веб-сервер ===
flask_app = Flask(__name__)

@flask_app.route('/') # Корневой маршрут
def home():
    return "Telegram Bot is running!", 200

@flask_app.route('/health')
def health():
    return {'status': 'ok'}, 200

# === ФУНКЦИЯ ЗАПУСКА Flask-сервера (работает в отдельном потоке) ===
def run_flask():
    print(f"🌍 Flask сервер запущен на порту {PORT}. Ожидание HTTP-запросов...")
    # debug=False важно для production
    flask_app.run(host='0.0.0.0', port=PORT, debug=False)

# === ОСНОВНОЙ ЗАПУСК ===
def main():
    # Запускаем Flask в отдельном потоке
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True  # Поток завершится, если основной процесс завершится
    flask_thread.start()

    # Создаём приложение бота
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_new_post))

    print(f"🚀 Бот запущен. Слушает канал {SOURCE_CHANNEL_ID}...")

    # === ОТПРАВИТЬ ОДИН ТЕСТОВЫЙ ОТЧЁТ СРАЗУ ПОСЛЕ ЗАПУСКА БОТА ===
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(send_daily_report_async(app))

    # === ЗАПУСТИТЬ БОТА В ОСНОВНОМ ПОТОКЕ (теперь это безопасно) ===
    app.run_polling()

if __name__ == "__main__":
    main()
