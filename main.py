import os
from datetime import datetime, timezone
from supabase import create_client
from telegram.ext import Application
from flask import Flask, jsonify, request

# Настройка логирования
import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# === Конфигурация из переменных окружения ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TARGET_CHANNEL_ID = int(os.getenv("TARGET_CHANNEL_ID"))
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
PORT = int(os.getenv("PORT", 10000))

# Инициализация Supabase
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
flask_app = Flask(__name__)

# Простой словарь для перевода заголовков (без внешних API)
TRANSLATION_MAP = {
    "Zelenskiy Vows Justice in Ukraine Corruption Probe Tied to Ex-Partner": "Зеленский обещает расследование коррупции при бывшем партнёре",
    "Germany Won't Make Military Service Mandatory (Unless It Has To)": "Германия не будет вводить обязательную военную службу",
    "From rare earths to antimony: A strategic approach to critical mineral supply": "Китай ограничивает экспорт стратегических минералов",
    "Moses parts the Red Sea: Israel’s strategic challenges as new routes emerge": "Новый мост в Красном море меняет логистику региона",
    "A New Path to Middle East Security": "Изменение баланса сил на Ближнем Востоке"
}

def translate_title(title):
    """Простой перевод заголовка по словарю"""
    for eng, rus in TRANSLATION_MAP.items():
        if eng.lower() in title.lower():
            return rus
    return title[:80] + "..." if len(title) > 80 else title

def get_recent_articles():
    """Получает статьи за последние 24 часа"""
    try:
        yesterday = datetime.now(timezone.utc) - timedelta(days=1)
        response = supabase.table("published_articles") \
            .select("*") \
            .gte("created_at", yesterday.isoformat()) \
            .order("created_at", desc=True) \
            .execute()
        return response.data
    except Exception as e:
        logger.error(f"Ошибка получения статей: {e}")
        return []

def generate_report(articles):
    """Генерирует краткую сводку до 1000 символов"""
    if not articles:
        return "Аналитическая записка\n14 ноября 2025 г.\n\nНет новых данных для анализа."

    # Формируем отчёт
    report_lines = [
        f"Аналитическая записка",
        f"{datetime.now(timezone.utc).strftime('%d %B %Y г.')}",
        "",
        "ТОП-5 критических событий:"
    ]

    for article in articles[:7]:  # Берём до 7 событий
        translated_title = translate_title(article["title"])
        url = article["url"]
        report_lines.append(f"• {translated_title} [{url}]")

    # Добавляем источники
    report_lines.append("")
    report_lines.append("Источники:")
    for article in articles[:5]:
        report_lines.append(article["url"])

    full_text = "\n".join(report_lines)
    return full_text[:1000]

async def send_report_to_telegram(report):
    """Отправляет отчёт в Telegram канал"""
    try:
        app = Application.builder().token(TELEGRAM_TOKEN).build()
        await app.bot.send_message(chat_id=TARGET_CHANNEL_ID, text=report)
        return True
    except Exception as e:
        logger.error(f"Ошибка отправки: {e}")
        return False

@flask_app.route("/trigger-report")
def trigger_report():
    """Обработчик запроса на генерацию отчёта"""
    try:
        logger.info("Запрос на генерацию отчёта...")
        
        articles = get_recent_articles()
        report = generate_report(articles)

        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        success = loop.run_until_complete(send_report_to_telegram(report))
        loop.close()

        if success:
            logger.info("Отчёт успешно отправлен")
            return jsonify({"status": "success"}), 200
        else:
            logger.error("Не удалось отправить отчёт")
            return jsonify({"status": "error"}), 500
            
    except Exception as e:
        logger.exception(f"Ошибка: {e}")
        return jsonify({"status": "error"}), 500

@flask_app.route("/")
def home():
    return "Bot is alive", 200

if __name__ == "__main__":
    flask_app.run(host="0.0.0.0", port=PORT, debug=False)
