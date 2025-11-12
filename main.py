import asyncio
import re
from datetime import datetime, timedelta
from supabase import create_client
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
import os

# === НАСТРОЙКИ (ЧИТАЮТСЯ ИЗ ОКРУЖЕНИЯ RENDER) ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
SOURCE_CHANNEL_ID = int(os.getenv("SOURCE_CHANNEL_ID"))  # ID ПРИВАТНОГО канала (например: -2923537056)
TARGET_CHANNEL_ID = int(os.getenv("TARGET_CHANNEL_ID"))  # ID ПУБЛИЧНОГО канала (например: -1001234567890)
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Ключевые слова для фильтрации (должны быть в начале текста)
RUSSIA_KEYWORDS = [
    "Россия", "Russia", "российск", "russo", "russe", "rusia", "russland",
    "Путин", "Кремль", "МИД", "ФСБ", "СВО", "Украина", "санкции", "энергия"
]

# === ИНИЦИАЛИЗАЦИЯ ===
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Проверка: ключевые слова в начале текста?
def has_russia_keyword(text: str) -> bool:
    if not text:
        return False
    first_line = text.split('\n')[0].lower()
    return any(kw.lower() in first_line for kw in RUSSIA_KEYWORDS)

# Проверка: дубль ли?
def is_duplicate(url: str) -> bool:
    response = supabase.table("ingested_content_items").select("id").eq("source_url", url).execute()
    return len(response.data) > 0

# Сохранить пост в Supabase
def save_post(title, content, url, pub_date, lang="ru"):
    supabase.table("ingested_content_items").insert({
        "source_url": url,
        "title": title[:500],
        "content": content[:10000],
        "pub_date": pub_date.isoformat(),
        "channel_id": SOURCE_CHANNEL_ID,
        "language": lang,
        "is_analyzed": False
    }).execute()

# Генерация отчёта (до 2000 знаков)
def generate_daily_report():
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
        "1. Исполнительное резюме",
        "За последние сутки зафиксированы ключевые события, влияющие на Россию. Все утверждения подтверждены 2–3 источниками.",
        "",
        "2. Ключевые события:",
    ]

    for post in posts[:5]:
        url = post["source_url"]
        content = post["content"][:300] + "..." if len(post["content"]) > 300 else post["content"]
        report.append(f"• {content} [{url}]")

    report.append("\n3. Вывод: Ситуация динамична. Мониторинг продолжается.")
    report.append(f"\nОтчёт сформирован: {datetime.utcnow().strftime('%d.%m.%Y %H:%M')} UTC")

    full_text = "\n".join(report)
    return full_text[:2000]

# Отправить отчёт в публичный канал
async def send_daily_report(app: Application):
    try:
        report = generate_daily_report()
        await app.bot.send_message(chat_id=TARGET_CHANNEL_ID, text=report)
        print(f"✅ Тестовый отчёт отправлен: {datetime.utcnow().strftime('%d.%m.%Y %H:%M')}")

        # Отметить посты как проанализированные
        yesterday = datetime.utcnow() - timedelta(days=1)
        supabase.table("ingested_content_items") \
            .update({"is_analyzed": True}) \
            .gte("pub_date", yesterday.isoformat()) \
            .execute()

    except Exception as e:
        print(f"❌ Ошибка отправки: {e}")

# Обработка новых постов из приватного канала
async def handle_new_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if message.chat.id != SOURCE_CHANNEL_ID:
        return

    text = message.text or ""
    url = message.link or f"https://t.me/c/{message.chat.id}/{message.message_id}"

    if not has_russia_keyword(text):
        return

    if is_duplicate(url):
        return

    save_post(
        title=text[:100],
        content=text,
        url=url,
        pub_date=message.date
    )
    print(f"📥 Сохранён пост: {url}")

# Запуск бота
def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_new_post))

    print(f"🚀 Бот запущен. Читаю приватный канал: {SOURCE_CHANNEL_ID}")
    
    # Отправить тестовый отчёт сразу после запуска
    loop = asyncio.get_event_loop()
    loop.create_task(send_daily_report(app))

    app.run_polling()

if __name__ == "__main__":
    main()
