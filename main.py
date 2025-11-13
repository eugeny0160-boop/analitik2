import os
import json
import re
from datetime import datetime, timedelta, timezone
from supabase import create_client
from telegram.ext import Application
from flask import Flask, jsonify, request
import logging
from collections import defaultdict

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

# Ключевые слова для 5 тем (в порядке приоритета: Россия → СВО → Пандемия → Криптовалюта → Мир)
CATEGORIES = {
    "Россия": ["россия", "российская", "москва", "путин", "кремль", "санкции", "рубль", "экономика россии"],
    "СВО": ["спецоперация", "военная операция", "украина", "война", "сво", "боевые действия", "вооруженные силы"],
    "Пандемия": ["коронавирус", "ковид", "пандемия", "вакцина", "эпидемия", "карантин", "covid"],
    "Криптовалюта": ["биткоин", "эфириум", "крипто", "блокчейн", "токен", "криптовалюта", "майнинг", "децентрализованный", "антипирий", "редкоземельный", "полупроводник"],
    "Общее положение в мире": ["глобальная экономика", "мировые лидеры", "международные отношения", "геополитика", "мировой рынок", "транспорт", "логистика", "коридор", "интеграция", "евразия", "азия", "сша", "европа", "ес", "ната", "британия", "франция", "германия"]
}

# Функция для получения статей за последние 24 часа
def get_recent_articles():
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
        logger.error(f"Ошибка получения статей: {e}")
        return []

# Функция для проверки дубликатов
def is_duplicate_report(content):
    try:
        today = datetime.now(timezone.utc).date().isoformat()
        response = supabase.table("analytical_reports") \
            .select("id") \
            .eq("report_date", today) \
            .eq("content", content) \
            .execute()
        return len(response.data) > 0
    except Exception as e:
        logger.error(f"Ошибка проверки дубликатов: {e}")
        return False

# Функция для классификации статей по 5 темам
def classify_articles(articles):
    categorized = {cat: [] for cat in CATEGORIES.keys()}
    used_urls = set()

    for article in articles:
        url = article["url"]
        if url in used_urls:
            continue
        used_urls.add(url)

        title_lower = article["title"].lower()
        for category, keywords in CATEGORIES.items():
            if any(keyword in title_lower for keyword in keywords):
                categorized[category].append(article)
                break  # Одна статья — одна категория

    # Берём по 1 статье на тему, в порядке приоритета
    result = []
    priority_order = ["Россия", "СВО", "Пандемия", "Криптовалюта", "Общее положение в мире"]
    
    for cat in priority_order:
        if categorized[cat]:
            result.append(categorized[cat][0])
            if len(result) >= 5:
                break

    # Если не хватает — заполняем из оставшихся
    if len(result) < 5:
        remaining = [a for a in articles if a["url"] not in used_urls]
        remaining.sort(key=lambda x: x["created_at"], reverse=True)
        result.extend(remaining[:5-len(result)])

    return result[:5]

# Генерация аналитической записки (строго по шаблону)
def generate_analytical_report(articles):
    if not articles:
        return "Аналитическая записка\n13 ноября 2025 г.\n\nНет новых событий за последние сутки."

    # 1. Заголовок и дата
    report = "Аналитическая записка\n"
    report += f"{datetime.now(timezone.utc).strftime('%d %B %Y г.')}\n\n"

    # 2. ТОП-5 событий (по 1 на тему)
    for article in articles:
        category = None
        for cat, keywords in CATEGORIES.items():
            if any(kw in article["title"].lower() for kw in keywords):
                category = cat
                break
        if not category:
            category = "Общее положение в мире"

        # Формируем строку события
        report += f"• {category}\n"
        report += f"  {article['title']}\n\n"

    # 3. Ссылки (только 5, без дублей)
    report += "\nСсылки:\n"
    unique_urls = []
    for article in articles:
        if article["url"] not in unique_urls:
            unique_urls.append(article["url"])
            report += f"{len(unique_urls)}. {article['url']}\n"
        if len(unique_urls) >= 5:
            break

    return report[:2000]

# Сохранение отчёта в базу
def save_report_to_db(report_content, source_count, article_ids):
    try:
        report_date = datetime.now(timezone.utc).date()
        data = {
            "report_date": report_date.isoformat(),
            "period_type": "daily",
            "content": report_content,
            "source_count": source_count,
            "is_sent": True,
            "categories": json.dumps({"top_articles": article_ids})
        }
        response = supabase.table("analytical_reports").insert(data).execute()
        return response.data[0]["id"] if response.data else None
    except Exception as e:
        logger.error(f"Ошибка сохранения отчёта: {e}")
        return None

# Отправка в Telegram
async def send_report_to_telegram(report):
    try:
        app = Application.builder().token(TELEGRAM_TOKEN).build()
        await app.bot.send_message(chat_id=TARGET_CHANNEL_ID, text=report)
        return True
    except Exception as e:
        logger.error(f"Ошибка отправки в Telegram: {e}")
        return False

# Главный эндпоинт
@flask_app.route("/trigger-report", methods=["GET"])
def trigger_report():
    try:
        logger.info("🔍 Запрос на генерацию аналитической записки...")
        
        articles = get_recent_articles()
        if not articles:
            report = "Аналитическая записка\n13 ноября 2025 г.\n\nНет новых событий за последние сутки."
            return jsonify({"status": "success", "message": "Нет новых статей"}), 200

        top_articles = classify_articles(articles)
        if not top_articles:
            report = "Аналитическая записка\n13 ноября 2025 г.\n\nНет подходящих событий для анализа."
            return jsonify({"status": "success", "message": "Нет подходящих событий"}), 200

        report = generate_analytical_report(top_articles)

        if is_duplicate_report(report):
            logger.info("ℹ️ Обнаружен дубликат отчёта.")
            return jsonify({"status": "success", "message": "Дубликат отчёта. Отправка отменена."}), 200

        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        success = loop.run_until_complete(send_report_to_telegram(report))
        loop.close()

        if not success:
            return jsonify({"status": "error", "message": "Не удалось отправить отчёт в Telegram"}), 500

        article_ids = [a["id"] for a in top_articles]
        report_id = save_report_to_db(report, len(top_articles), article_ids)

        if report_id:
            logger.info(f"✅ Успешно отправлен отчёт ID: {report_id}")
            return jsonify({
                "status": "success",
                "message": "Аналитическая записка успешно сгенерирована и отправлена",
                "report_id": report_id,
                "article_count": len(top_articles)
            }), 200
        else:
            logger.warning("⚠️ Отчёт отправлен, но не сохранён в базу.")
            return jsonify({
                "status": "partial",
                "message": "Отчёт отправлен, но не сохранён в базу"
            }), 200
            
    except Exception as e:
        logger.exception(f"❌ Критическая ошибка: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

# Проверка здоровья
@flask_app.route("/health", methods=["GET"])
def health_check():
    return jsonify({"status": "healthy"}), 200

@flask_app.route("/", methods=["GET"])
def home():
    return "✅ Аналитический сервис работает. Используйте /trigger-report.", 200

if __name__ == "__main__":
    flask_app.run(host="0.0.0.0", port=PORT, debug=False)
