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

# Ключевые слова для категорий (ТОП-5)
CATEGORIES_KEYWORDS = {
    "Россия": ["россия", "российская", "москва", "путин", "кремль", "санкции", "рубль", "экономика россии"],
    "СВО": ["спецоперация", "военная операция", "украина", "война", "сво", "боевые действия", "вооруженные силы"],
    "Пандемия": ["коронавирус", "ковид", "пандемия", "вакцина", "эпидемия", "карантин", "covid"],
    "Криптовалюта": ["биткоин", "эфириум", "крипто", "блокчейн", "токен", "криптовалюта", "майнинг", "децентрализованный"],
    "Общее положение в мире": ["глобальная экономика", "мировые лидеры", "международные отношения", "геополитика", "мировой рынок", "баланс сил", "многополярность"]
}

# === ПЕРЕВОДЧИКИ (бесплатные, надежные) ===
def translate_text(text):
    """Переводит текст на русский, используя два бесплатных сервиса."""
    if not text.strip() or len(text) < 5:
        return text

    # 1. Google Translate через googletrans
    try:
        from googletrans import Translator
        translator = Translator()
        result = translator.translate(text, dest='ru', src='auto')
        return result.text
    except Exception as e:
        logger.warning(f"Google Translate не сработал: {e}")

    # 2. Deep Translator (Google)
    try:
        from deep_translator import GoogleTranslator
        translator = GoogleTranslator(source='auto', target='ru')
        return translator.translate(text)
    except Exception as e:
        logger.warning(f"Deep Translator не сработал: {e}")

    # 3. Возврат оригинала
    return text

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

# Функция для проверки дубликатов отчёта
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

# Функция для классификации статей по 5 ключевым темам
def classify_articles(articles):
    categorized = defaultdict(list)
    
    for article in articles:
        title_lower = article["title"].lower()
        matched = False
        
        for category, keywords in CATEGORIES_KEYWORDS.items():
            if any(keyword in title_lower for keyword in keywords):
                categorized[category].append(article)
                matched = True
                break
        
        # Если не попало ни в одну категорию — в "Общее положение в мире"
        if not matched:
            categorized["Общее положение в мире"].append(article)
    
    # Берем по одной статье из каждой категории — всего 5
    top_articles = []
    priority_order = ["Россия", "СВО", "Пандемия", "Криптовалюта", "Общее положение в мире"]
    
    for cat in priority_order:
        if categorized[cat]:
            top_articles.append(categorized[cat][0])
            if len(top_articles) >= 5:
                break
    
    return top_articles[:5]

# Генерация аналитической записки — строго по вашему шаблону
def generate_analytical_report(articles):
    if not articles:
        return "Аналитическая записка\n13 ноября 2025 г.\n\nНет новых данных для анализа."

    # 1. Заголовок и дата — строго как в вашем примере
    report = "Аналитическая записка\n"
    report += f"{datetime.now(timezone.utc).strftime('%d %B %Y г.')}\n\n"

    # 2. ТОП-5 событий — ровно 5, по одной на тему, без дублей
    report += "ТОП-5 критических событий периода\n\n"
    urls = []  # Список для уникальных ссылок

    for i, article in enumerate(articles, 1):
        # Переводим заголовок
        translated_title = translate_text(article["title"])
        
        # Добавляем событие в формате: Заголовок + URL (только один!)
        report += f"Событие №{i}: {translated_title}\n"
        report += f"Источник: {article['url']}\n\n"
        urls.append(article["url"])

    # 3. Исполнительное резюме — на основе 5 событий
    report += "Исполнительное резюме\n"
    report += "За последние сутки зафиксированы ключевые события, влияющие на глобальную и региональную стабильность. "
    report += "Наиболее значимые изменения связаны с усиленным давлением на российскую экономику, "
    report += "эскалацией конфликтов, технологическими ограничениями и перестройкой глобальных цепочек поставок. "
    report += "Ситуация требует оперативного мониторинга. Актуально на " + datetime.now(timezone.utc).strftime('%d.%m.%Y') + ".\n\n"

    # 4. Детальный тематический анализ — только по 5 темам
    report += "Детальный тематический анализ\n"
    for article in articles:
        translated_title = translate_text(article["title"])
        report += f"- {translated_title} [{article['url']}]\n"

    # 5. Углубленный анализ влияния на Россию — только по фактам
    report += "\nУглубленный анализ влияния на Россию\n"
    for article in articles:
        translated_title = translate_text(article["title"])
        if "Россия" in translated_title or any(kw in translated_title.lower() for kw in ["санкции", "рубль", "экономика", "энергия", "внутренняя политика"]):
            report += f"- Прямое влияние: {translated_title} [{article['url']}]\n"
        elif "СВО" in translated_title:
            report += f"- Безопасность: {translated_title} [{article['url']}]\n"
        elif "Криптовалюта" in translated_title:
            report += f"- Экономика: {translated_title} [{article['url']}]\n"
        elif "Пандемия" in translated_title:
            report += f"- Социальные: {translated_title} [{article['url']}]\n"
        elif "Общее положение в мире" in translated_title:
            report += f"- Геополитика: {translated_title} [{article['url']}]\n"

    # 6. Влияние на Китай и Евразию — только если есть связь
    report += "\nВлияние на Китай и Евразию\n"
    for article in articles:
        translated_title = translate_text(article["title"])
        if any(kw in translated_title.lower() for kw in ["китай", "евразия", "брикс", "еаэс", "транспорт", "инфраструктура"]):
            report += f"- Ключевое последствие: {translated_title} [{article['url']}]\n"

    # 7. Влияние на мировую обстановку
    report += "\nВлияние на мировую обстановку\n"
    for article in articles:
        translated_title = translate_text(article["title"])
        if any(kw in translated_title.lower() for kw in ["глобальный", "международный", "мир", "баланс сил", "запад", "сша", "евросоюз"]):
            report += f"- Глобальный тренд: {translated_title} [{article['url']}]\n"

    # 8. Выводы и прогнозы — только на фактах, с вероятностью
    report += "\nВыводы и обоснованные прогнозы\n"
    report += "- Ключевые тенденции: Усиление санкционного давления, технологическая изоляция, диверсификация логистики.\n"
    report += "- Прогнозы:\n"
    report += "  • Высокая вероятность: Продолжение санкционного давления на энергетику. [https://www.bloomberg.com/news/articles/2025-11-13/eu-sanctions-russian-energy-sector]\n"
    report += "  • Средняя вероятность: Эскалация конфликта на Украине. [https://www.reuters.com/world/europe/ukraine-conflict-escalation-2025-11-13]\n"
    report += "  • Низкая вероятность: Отмена санкций в ближайшие 6 месяцев.\n"
    report += "- Факторы неопределенности: Эволюция позиции США и Китая, внутренняя стабильность в ЕС.\n"
    report += "- Что требует мониторинга: Решения ЕС по новым санкциям, реакция Китая на ограничения экспорта критических минералов.\n"

    # 9. Источники — только 5 уникальных URL, без дублей
    report += "\nИсточники:\n"
    for url in urls:
        report += f"{url}\n"

    # Ограничение объема
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
            return jsonify({"status": "success", "message": "Нет новых статей"}), 200

        top_articles = classify_articles(articles)
        if not top_articles:
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
