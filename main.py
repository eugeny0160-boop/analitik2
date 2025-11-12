import asyncio
from datetime import datetime
from supabase import create_client
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
import os

# === ЧТЕНИЕ ПЕРЕМЕННЫХ ИЗ ОКРУЖЕНИЯ (Render) ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
SOURCE_CHANNEL_ID = int(os.getenv("SOURCE_CHANNEL_ID"))  # ID приватного канала
TARGET_CHANNEL_ID = int(os.getenv("TARGET_CHANNEL_ID"))   # ID публичного канала
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# === ИНИЦИАЛИЗАЦИЯ ===
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Сохранить пост в базу (без проверки на дубль)
def save_post(title, content, url, pub_date):
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

# Генерация отчёта (объединяет все непроанализированные посты)
def generate_daily_report():
    try:
        # Получаем ВСЕ посты, которые ещё не проанализированы
        response = supabase.table("ingested_content_items") \
            .select("*") \
            .eq("is_analyzed", False) \
            .order("pub_date", desc=True) \
            .execute()

        posts = response.data
        if not posts:
            return "Нет новых данных для анализа."

        # Формируем отчёт
        report = [
            f"📊 Аналитический отчёт (всего постов: {len(posts)})",
            f"Сформирован: {datetime.utcnow().strftime('%d.%m.%Y %H:%M')} UTC",
            "",
            "📌 Последние посты:",
        ]

        for post in posts:
            url = post["source_url"]
            content = post["content"] or "Нет текста"
            report.append(f"• {content} [{url}]")

        full_text = "\n".join(report)
        return full_text[:2000]  # Ограничиваем до 2000 знаков

    except Exception as e:
        return f"❌ Ошибка генерации отчёта: {e}"

# Отправка отчёта
async def send_daily_report(app: Application):
    try:
        report = generate_daily_report()
        await app.bot.send_message(chat_id=TARGET_CHANNEL_ID, text=report)
        print(f"✅ Тестовый отчёт отправлен: {datetime.utcnow().strftime('%d.%m.%Y %H:%M')}")

        # Отмечаем все посты как проанализированные
        supabase.table("ingested_content_items") \
            .update({"is_analyzed": True}) \
            .eq("is_analyzed", False) \
            .execute()

    except Exception as e:
        print(f"❌ Ошибка отправки отчёта: {e}")

# Обработка новых постов из Telegram
async def handle_new_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    # Проверяем, что пост из нужного приватного канала
    if message.chat.id != SOURCE_CHANNEL_ID:
        return

    text = message.text or ""
    # Создаём ссылку на пост
    url = message.link or f"https://t.me/c/{message.chat.id}/{message.message_id}"

    # Сохраняем БЕЗ всяких фильтров
    save_post(
        title=text[:100],
        content=text,
        url=url,
        pub_date=message.date
    )

# Запуск бота
def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    # Обработчик всех текстовых сообщений
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_new_post))

    print(f"🚀 Бот запущен. Слушает приватный канал {SOURCE_CHANNEL_ID}...")

    # === ОТПРАВИТЬ ОДИН ТЕСТОВЫЙ ОТЧЁТ СРАЗУ ПОСЛЕ ЗАПУСКА ===
    loop = asyncio.get_event_loop()
    loop.create_task(send_daily_report(app))

    app.run_polling()

if __name__ == "__main__":
    main()
