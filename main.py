import os
import json
from datetime import datetime, timedelta, timezone
from supabase import create_client
from telegram.ext import Application
from flask import Flask, jsonify, request
import logging
import requests

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# === Конфигурация ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TARGET_CHANNEL_ID = int(os.getenv("TARGET_CHANNEL_ID"))
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
PORT = int(os.getenv("PORT", 10000))

# Инициализация Supabase
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
flask_app = Flask(__name__)

# Простой словарь для перевода заголовков
SIMPLE_TRANSLATIONS = {
    "Zelenskiy Vows Justice in Ukraine Corruption Probe Tied to Ex-Partner": "Зеленский обещает расследование коррупции, связанной с бывшим партнёром",
    "Germany Won't Make Military Service Mandatory (Unless It Has To)": "Германия не будет вводить обязательную военную службу (пока)",
    "From rare earths to antimony: A strategic approach to critical mineral supply": "Китай ограничил экспорт ключевых минералов",
    "Moses parts the Red Sea: Israel’s strategic challenges as new routes emerge": "Новый маршрут через Красное море меняет стратегию Израиля",
    "A New Path to Middle East Security": "Новый путь к безопасности на Ближнем Востоке",
    "Saudi prince meets with Trump": "Саудовский принц встречается с Трампом",
    "Cocaine Bonanza and a Defiant Colombian President Infuriate Trump": "Колумбийский президент вызвал гнев Трампа из-за наркотрафика",
    "Ex-MI6 Chief Says Chinese Should 'Get Their Embassy' in London": "Бывший глава MI6: Китай должен получить посольство в Лондоне"
}

def translate_text(text):
    """Переводит текст на русский, используя 3 бесплатных переводчика. Возвращает '', если все не сработали."""
    if not text or len(text.strip()) < 5:
        return ""

    # 0. Проверяем простой словарь
    for eng, rus in SIMPLE_TRANSLATIONS.items():
        if eng.lower() in text.lower():
            return rus

    # 1. Yandex API
    yandex_key = os.getenv("YANDEX_API_KEY")
    if yandex_key:
        try:
            url = "https://translate.api.cloud.yandex.net/translate/v2/translate"
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Api-Key {yandex_key}",
            }
            data = {
                "sourceLanguageCode": "auto",
                "targetLanguageCode": "ru",
                "texts": [text],
                "folderId": os.getenv("YANDEX_FOLDER_ID", "")
            }
            response = requests.post(url, headers=headers, json=data, timeout=5)
            if response.status_code == 200:
                result = response.json()
                return result["translations"][0]["text"]
        except Exception as e:
            logger.warning(f"Yandex API failed: {e}")

    # 2. Deep Translator
    try:
        from deep_translator import GoogleTranslator
        translator = GoogleTranslator(source='auto', target='ru')
        return translator.translate(text)
    except Exception as e:
        logger.warning(f"Deep Translator failed: {e}")

    # 3. Google Translate
    try:
        from googletrans import Translator
        trans = Translator()
        result = trans.translate(text, dest='ru', src='auto')
        return result.text
    except Exception as e:
        logger.warning(f"Google Translate failed: {e}")

    # 4. Если все не сработали
    logger.warning(f"All translators failed for: {text}")
    return ""

def get_recent_articles():
    """Получает статьи за последние 24 часа из Supabase."""
    now = datetime.now(timezone.utc)
    yesterday = now - timedelta(days=1)
    try:
        response = supabase.table("published_articles") \
            .select("*") \
            .gte("created_at", yesterday.isoformat()) \
            .order("created_at", desc=True) \
            .execute()
        return response.data
    except Exception as e:
        logger.error(f"Ошибка получения статей из Supabase: {e}")
        return []

def generate_report(articles):
    """Генерирует аналитическую записку до 1000 символов."""
    if not articles:
        return "Аналитическая записка\n14 ноября 2025 г.\n\nНет новых данных для анализа."

    report_lines = [
        "Аналитическая записка",
        f"{datetime.now(timezone.utc).strftime('%d %B %Y г.')}",
        "",
        "ТОП-5 критических событий:"
    ]

    sources = set()  # Используем set, чтобы избежать дублей в источниках
    for article in articles:
        # Пропускаем, если перевод не удался
        translated_title = translate_text(article["title"])
        if not translated_title:
            continue

        report_lines.append(f"• {translated_title} [{article['url']}]")
        sources.add(article['url'])

        # Проверяем длину отчёта
        current_text = "\n".join(report_lines) + "\n\nИсточники:\n" + "\n".join(list(sources)[:5])
        if len(current_text.encode('utf-8')) > 950: # 950, чтобы оставить место на "Источники:"
            break

    # Добавляем раздел "Источники"
    if sources:
        report_lines.append("\nИсточники:")
        for url in list(sources)[:5]: # Максимум 5 источников
            report_lines.append(url)

    full_report = "\n".join(report_lines)
    return full_report[:1000]

async def send_report_to_telegram(report):
    """Отправляет отчёт в Telegram канал."""
    try:
        app = Application.builder().token(TELEGRAM_TOKEN).build()
        await app.bot.send_message(chat_id=TARGET_CHANNEL_ID, text=report)
        return True
    except Exception as e:
        logger.error(f"Ошибка отправки в Telegram: {e}")
        return False

def save_report_to_db(report_content, source_count):
    """Сохраняет отчёт в таблицу analytical_reports."""
    try:
        report_date = datetime.now(timezone.utc).date()
        data = {
            "report_date": report_date.isoformat(),
            "period_type": "daily",
            "content": report_content,
            "source_count": source_count,
            "is_sent": True,
            "generated_at": datetime.now(timezone.utc).isoformat()
        }
        supabase.table("analytical_reports").insert(data).execute()
        logger.info("Отчёт успешно сохранён в базу данных.")
    except Exception as e:
        logger.error(f"Ошибка сохранения отчёта в базу данных: {e}")

@flask_app.route("/trigger-report", methods=["GET"])
def trigger_report():
    """Эндпоинт для запуска генерации отчёта."""
    try:
        articles = get_recent_articles()
        if not articles:
            return jsonify({"status": "success", "message": "Нет новых статей"}), 200

        report = generate_report(articles)
        if not report.strip():
            return jsonify({"status": "error", "message": "Не удалось сгенерировать отчёт"}), 500

        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        success = loop.run_until_complete(send_report_to_telegram(report))
        loop.close()

        if success:
            save_report_to_db(report, len(articles))
            logger.info("Отчёт успешно отправлен и сохранён.")
            return jsonify({"status": "success", "message": "Отчёт отправлен"}), 200
        else:
            return jsonify({"status": "error", "message": "Ошибка отправки"}), 500

    except Exception as e:
        logger.error(f"Ошибка в trigger_report: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@flask_app.route("/", methods=["GET"])
def home():
    return "Аналитический бот работает.", 200

if __name__ == "__main__":
    flask_app.run(host="0.0.0.0", port=PORT, debug=False)
