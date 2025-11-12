import asyncio
import threading
import re
from datetime import datetime, timedelta
from supabase import create_client
from telegram.ext import Application, MessageHandler, filters
from telegram import Update
import os
from flask import Flask, jsonify

# === Настройки ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
SOURCE_CHANNEL_ID = int(os.getenv("SOURCE_CHANNEL_ID"))
TARGET_CHANNEL_ID = int(os.getenv("TARGET_CHANNEL_ID"))
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

# === НОВАЯ ФУНКЦИЯ: Генерация структурированной аналитической записки ===
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

        # --- Группировка по категориям (упрощённая) ---
        categories = {
            " geopolitic ": [],
            " economy ": [],
            " security ": [],
            " energy ": [],
            " tech ": [],
            " other ": []
        }

        for p in posts:
            content_lower = p['content'].lower() if p['content'] else ""
            url = p['source_url']
            # Извлекаем первые 100 символов как "заголовок"
            snippet = (p['content'] or "Нет текста")[:100] + ("..." if len(p['content'] or "") > 100 else "")
            
            # Классификация по ключевым словам
            if any(k in content_lower for k in ["диплом", "международ", "переговор", "встреч", "власть", "полит", "власть"]):
                categories[" geopolitic "].append(f"• {snippet} [{url}]")
            elif any(k in content_lower for k in ["эконом", "цен", "торговл", "бирж", "валют", "инфляц", "бюджет", "финанс"]):
                categories[" economy "].append(f"• {snippet} [{url}]")
            elif any(k in content_lower for k in ["войн", "армия", "безопасн", "террор", "развед", "погранич"]):
                categories[" security "].append(f"• {snippet} [{url}]")
            elif any(k in content_lower for k in ["нефть", "газ", "энерг", "ресурс", "электро", "уголь"]):
                categories[" energy "].append(f"• {snippet} [{url}]")
            elif any(k in content_lower for k in ["технолог", "искусствен", "спутник", "кибер", "инновац"]):
                categories[" tech "].append(f"• {snippet} [{url}]")
            else:
                categories[" other "].append(f"• {snippet} [{url}]")

        # --- Формирование отчёта ---
        report_lines = [
            f"📊 <b>Аналитическая записка за {yesterday.strftime('%d.%m.%Y')}</b>",
            f"Сформировано: {datetime.utcnow().strftime('%d.%m.%Y %H:%M')} UTC",
            "",
            "<b>1. Исполнительное резюме</b>",
            f"За последние 24 часа зафиксировано {len(posts)} событий, касающихся международной обстановки и России. Ниже представлена структурированная сводка.",
            "",
        ]

        # Добавляем категории с постами
        for category, items in categories.items():
            if items: # Только если есть посты в категории
                report_lines.append(f"<b>{category.upper()}</b>")
                report_lines.extend(items)
                report_lines.append("") # Пустая строка между категориями

        full_text = "\n".join(report_lines)
        return full_text[:4000] # Ограничиваем до 4000 знаков для Telegram

    except Exception as e:
        return f"❌ Ошибка генерации отчёта: {e}"

# Отдельная асинхронная функция для отправки отчёта
async def send_report_async():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    try:
        report = generate_report()
        await app.bot.send_message(chat_id=TARGET_CHANNEL_ID, text=report, parse_mode="HTML")
        print("✅ Аналитическая записка отправлена")

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

# Обработчик для КАНАЛЬНЫХ постов (channel_post)
async def handle_channel_post(update: Update, context):
    post = update.channel_post
    if post is None: return

    if post.chat.id != SOURCE_CHANNEL_ID: return

    url = post.link or f"https://t.me/c/{post.chat.id}/{post.message_id}"
    save_post(post.text[:100], post.text, url, post.date)

# === Flask для порта ===
flask_app = Flask(__name__)

@flask_app.route("/") 
def home():
    return "Bot is alive", 200

@flask_app.route("/trigger-report")
def trigger_report():
    print("🔍 Получен запрос на генерацию отчёта от cron-job.org")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    success = loop.run_until_complete(send_report_async())
    loop.close()
    if success:
        return jsonify({"status": "success", "message": "Отчёт успешно отправлен"}), 200
    else:
        return jsonify({"status": "error", "message": "Ошибка при отправке отчёта"}), 500

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
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_channel_post))
    
    print("🚀 Бот запущен...")
    # Отправляем отчёт сразу при запуске (как тест)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(send_report_async())
    loop.close()
    
    # Запускаем polling
    app.run_polling()

if __name__ == "__main__":
    main()
