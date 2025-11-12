import asyncio
from datetime import datetime, timedelta
from supabase import create_client
from telegram.ext import Application, MessageHandler, filters
from telegram import Update
import os
from flask import Flask, request, jsonify
from telegram.request import HTTPXRequest

# === Настройки ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
SOURCE_CHANNEL_ID = int(os.getenv("SOURCE_CHANNEL_ID")) # ID вашего НОВОГО приватного канала
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
        # Получаем все непроанализированные посты за последние 24 часа
        resp = supabase.table("ingested_content_items") \
            .select("*") \
            .gte("pub_date", yesterday.isoformat()) \
            .eq("is_analyzed", False) \
            .order("pub_date", desc=True) \
            .execute()

        posts = resp.data
        if not posts:
            return "Нет новых данных за последние 24 часа."

        # Группируем по source_url (по источникам)
        sources = {}
        for post in posts:
            url = post["source_url"]
            if url not in sources:
                sources[url] = []
            sources[url].append(post["content"] or "Без текста")

        # Формируем отчёт
        report_lines = [
            f"1. Исполнительное резюме",
            f"За отчётный период проанализировано {len(sources)} источников.",
            f"Основные события касаются геополитической и экономической динамики в регионе.",
            f"",
            f"2. Обзор по источникам",
        ]

        for url, contents in sources.items():
            report_lines.append(f"• Источник: {url}")
            for content in contents[:1]:  # Берём только первый пост от источника
                clean_content = (content[:290] + "...") if len(content) > 290 else content
                report_lines.append(f"  – {clean_content}")

        report_lines.append("")
        report_lines.append("3. Вывод")
        report_lines.append("Ситуация остаётся динамичной. Требуется мониторинг ключевых событий.")
        report_lines.append(f"Отчёт сформирован: {datetime.utcnow().strftime('%d.%m.%Y %H:%M')} UTC")

        full_text = "\n".join(report_lines)
        return full_text[:2000]

    except Exception as e:
        return f"❌ Ошибка генерации отчёта: {e}"

# Отдельная асинхронная функция для отправки отчёта
async def send_report_async():
    # Создаём временное приложение для отправки отчёта
    app = Application.builder().token(TELEGRAM_TOKEN).build()
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
        return True
    except Exception as e:
        print(f"❌ Ошибка отправки: {e}")
        return False

# === Flask для порта и Webhook ===
flask_app = Flask(__name__)

@flask_app.route("/") 
def home():
    return "Bot is alive", 200

# Маршрут для получения webhook от Telegram
@flask_app.route(f'/{os.getenv("TELEGRAM_TOKEN")}', methods=['POST'])
def webhook():
    try:
        # Получаем JSON-данные из запроса
        update_json = request.get_json()
        update = Update.de_json(update_json)

        # Обрабатываем пост, если он из нужного канала
        if update.channel_post and update.channel_post.chat.id == SOURCE_CHANNEL_ID:
            post = update.channel_post
            url = post.link or f"https://t.me/c/{post.chat.id}/{post.message_id}"
            save_post(post.text[:100], post.text, url, post.date)

        # Всегда возвращаем 200 OK
        return jsonify({"status": "ok"}), 200
    except Exception as e:
        print(f"❌ Ошибка обработки webhook: {e}")
        return jsonify({"error": str(e)}), 500

# Маршрут для запуска отчёта вручную
@flask_app.route("/trigger-report")
def trigger_report():
    print("🔍 Получен запрос на генерацию отчёта от cron-job.org или вручную")
    # Создаём новый event loop для выполнения асинхронной функции
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        success = loop.run_until_complete(send_report_async())
    finally:
        loop.close() # Закрываем loop после выполнения задачи
    
    if success:
        return jsonify({"status": "success", "message": "Отчёт успешно отправлен"}), 200
    else:
        return jsonify({"status": "error", "message": "Ошибка при отправке отчёта"}), 500

# === Запуск Flask ===
def main():
    print(f"🌍 Flask сервер запущен на порту {PORT}. Ожидание webhook на /{TELEGRAM_TOKEN}...")
    # debug=False важно для production
    flask_app.run(host='0.0.0.0', port=PORT, debug=False)

if __name__ == "__main__":
    main()
