import asyncio
from datetime import datetime, timedelta
from supabase import create_client
from telegram.ext import Application, MessageHandler, filters
from telegram import Update
import os
from flask import Flask, request, jsonify

# === Настройки ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
SOURCE_CHANNEL_ID = int(os.getenv("SOURCE_CHANNEL_ID"))  # Приватный канал, откуда читаем
TARGET_CHANNEL_ID = int(os.getenv("TARGET_CHANNEL_ID"))  # Публичный канал, куда отправляем отчёты
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
PORT = int(os.getenv("PORT", 10000))  # Обязательно используем PORT от Render

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def is_duplicate(url):
    try:
        resp = supabase.table("ingested_content_items").select("id").eq("source_url", url).execute()
        return len(resp.data) > 0
    except Exception as e:
        print(f"❌ Ошибка проверки дубликата: {e}")
        return False

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
        print(f"❌ Ошибка сохранения {url}: {e}")

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
        if not posts:
            return "Нет новых данных за последние 24 часа."

        sources = {}
        for post in posts:
            url = post["source_url"]
            if url not in sources:
                sources[url] = []
            sources[url].append(post["content"] or "Без текста")

        report_lines = [
            f"1. Исполнительное резюме",
            f"Проанализировано {len(sources)} источников.",
            f"Основные события касаются геополитической и экономической динамики в регионе.",
            f"",
            f"2. Обзор по источникам",
        ]

        for url, contents in sources.items():
            report_lines.append(f"• Источник: {url}")
            for content in contents[:1]:
                clean_content = (content[:290] + "...") if len(content) > 290 else content
                report_lines.append(f"  – {clean_content}")

        report_lines.append("")
        report_lines.append("3. Вывод")
        report_lines.append("Ситуация требует мониторинга.")
        report_lines.append(f"Отчёт сформирован: {datetime.utcnow().strftime('%d.%m.%Y %H:%M')} UTC")

        full_text = "\n".join(report_lines)
        return full_text[:2000]

    except Exception as e:
        return f"❌ Ошибка генерации отчёта: {e}"

async def send_report_async():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    try:
        report = generate_report()
        await app.bot.send_message(chat_id=TARGET_CHANNEL_ID, text=report)
        print("✅ Отчёт отправлен")

        supabase.table("ingested_content_items") \
            .update({"is_analyzed": True}) \
            .gte("pub_date", (datetime.utcnow() - timedelta(days=1)).isoformat()) \
            .eq("is_analyzed", False) \
            .execute()
        return True
    except Exception as e:
        print(f"❌ Ошибка отправки: {e}")
        return False

# === Flask сервер ===
flask_app = Flask(__name__)

@flask_app.route("/")
def home():
    return "🤖 Финансист-Аналитик: Бот активен и слушает webhook.", 200

# Webhook для Telegram — ОБЯЗАТЕЛЬНО: /ваш_токен
@flask_app.route(f'/{TELEGRAM_TOKEN}', methods=['POST'])
def webhook():
    try:
        print("🔍 Получен webhook от Telegram...")
        update_json = request.get_json()
        if not update_json:
            print("⚠️ Запрос не содержит JSON")
            return jsonify({"error": "Empty JSON"}), 400

        print(f"📨 Получено обновление: {update_json}")

        update = Update.de_json(update_json)

        if update.channel_post:
            print(f"💬 Найден channel_post от чата {update.channel_post.chat.id}")
            if update.channel_post.chat.id == SOURCE_CHANNEL_ID:
                print("✅ Пост из нужного канала.")
                post = update.channel_post
                url = post.link or f"https://t.me/c/{post.chat.id}/{post.message_id}"
                save_post(post.text[:100], post.text, url, post.date)
            else:
                print(f"❌ Пост из другого канала: {update.channel_post.chat.id}")
        else:
            print("💬 Обновление не содержит channel_post.")

        return jsonify({"status": "ok"}), 200

    except Exception as e:
        print(f"❌ Ошибка обработки webhook: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@flask_app.route("/trigger-report")
def trigger_report():
    print("🔍 Запрос на генерацию отчёта...")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        success = loop.run_until_complete(send_report_async())
    finally:
        loop.close()

    if success:
        return jsonify({"status": "success", "message": "Отчёт успешно отправлен"}), 200
    else:
        return jsonify({"status": "error", "message": "Ошибка при отправке отчёта"}), 500

def main():
    print(f"🌍 Flask сервер запущен на порту {PORT}. Ожидание webhook на /{TELEGRAM_TOKEN}...")
    flask_app.run(host='0.0.0.0', port=PORT, debug=False)

if __name__ == "__main__":
    main()
