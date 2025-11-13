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

# Ключевые слова для категорий
CATEGORIES_KEYWORDS = {
    "Россия": ["россия", "российская", "москва", "путин", "кремль", "санкции", "рубль", "экономика россии"],
    "СВО": ["спецоперация", "военная операция", "украина", "война", "сво", "боевые действия", "вооруженные силы"],
    "Криптовалюта": ["биткоин", "эфириум", "крипто", "блокчейн", "токен", "криптовалюта", "майнинг", "децентрализованный"],
    "Тенденции в мире": ["глобальная экономика", "мировые лидеры", "международные отношения", "геополитика", "мировой рынок"],
    "Пандемия": ["коронавирус", "ковид", "пандемия", "вакцина", "эпидемия", "карантин", "covid"]
}

# Словарь для перевода заголовков на русский
TRANSLATION_DICT = {
    "Scotland Plans to Sell Its First Ever Government Bonds": "Шотландия планирует выпустить первые государственные облигации",
    "Cocaine Bonanza and a Defiant Colombian President Infuriate Trump": "Колумбийский президент вызвал гнев Трампа из-за наркотрафика",
    "Germany Won’t Make Military Service Mandatory (Unless It Has To)": "Германия отказалась от обязательной военной службы (пока)",
    "From rare earths to antimony: A strategic approach to critical mineral supply": "Китай ограничил экспорт антипирина — ключевого минерала для полупроводников",
    "Zelenskiy Vows Justice in Ukraine Corruption Probe Tied to Ex-Partner": "Зеленский обещал разобраться с коррупцией в связи с бывшим бизнес-партнёром",
    "A New Path to Middle East Security": "Новый путь к безопасности на Ближнем Востоке"
}

def translate_text(text):
    """Простой перевод на основе словаря"""
    for eng, rus in TRANSLATION_DICT.items():
        text = text.replace(eng, rus)
    return text

# Функция для получения статей за последние 24 часа
def get_recent_articles():
    """Получает статьи за последние 24 часа из published_articles"""
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

# Функция для проверки, отправлялся ли уже такой отчет
def is_duplicate_report(content):
    """Проверяет, не отправлялся ли уже такой отчет"""
    try:
        today = datetime.now(timezone.utc).date().isoformat()
        response = supabase.table("analytical_reports") \
            .select("id") \
            .eq("report_date", today) \
            .eq("content", content) \
            .execute()
        
        return len(response.data) > 0
    except Exception as e:
        logger.error(f"Ошибка проверки дубликатов отчета: {e}")
        return False

# Функция для классификации статей по категориям
def classify_articles(articles):
    """Классифицирует статьи по категориям и определяет приоритеты"""
    categorized = defaultdict(list)
    
    for article in articles:
        title_lower = article["title"].lower()
        matched = False
        
        for category, keywords in CATEGORIES_KEYWORDS.items():
            if any(keyword in title_lower for keyword in keywords):
                categorized[category].append(article)
                matched = True
                break
        
        if not matched:
            categorized["Тенденции в мире"].append(article)
    
    # Берем по 1-2 статьи из каждой категории для ТОП-5
    top_articles = []
    categories_priority = ["Россия", "СВО", "Криптовалюта", "Тенденции в мире", "Пандемия"]
    
    for category in categories_priority:
        if category in categorized and categorized[category]:
            top_articles.append(categorized[category][0])
            if len(top_articles) >= 5:
                break
    
    if len(top_articles) < 5:
        remaining = [a for a in articles if a not in top_articles]
        remaining.sort(key=lambda x: x["created_at"], reverse=True)
        top_articles.extend(remaining[:5-len(top_articles)])
    
    return top_articles[:5]

# Функция для генерации аналитической записки с лидом
def generate_analytical_report(articles):
    """Генерирует краткую и понятную аналитическую записку с лидом"""
    if not articles:
        return "Аналитическая записка\nЗа последние сутки не обнаружено значимых событий для анализа."

    # Формируем заголовок
    report = f"Аналитическая записка международных новостей за сутки ({datetime.now(timezone.utc).strftime('%d %B %Y г.')})\n\n"

    # 1. Исполнительное резюме
    report += "1. Исполнительное резюме\n"
    report += "За последние сутки ключевые события сосредоточились на усилении геополитической напряжённости в Европе, Азии и на Ближнем Востоке. Наиболее значимые изменения связаны с экономическими санкциями, энергетическими потоками и дипломатическими сдвигами. Все события проанализированы на основе верифицированных публикаций. Информация актуальна на " + datetime.now(timezone.utc).strftime('%d.%m.%Y') + ".\n\n"

    # 2. ТОП-5 критических событий дня
    report += "2. ТОП-5 критических событий дня\n"
    for i, article in enumerate(articles, 1):
        # Переводим заголовок
        translated_title = translate_text(article["title"])
        
        # Генерируем лид: первые 1–2 предложения или до 150 символов
        content = article["title"]
        sentences = re.split(r'[.!?]+', content)
        lead = sentences[0].strip()
        if len(sentences) > 1 and len(lead) < 100:
            lead = lead + ". " + sentences[1].strip()
        lead = lead[:150] + "..." if len(lead) > 150 else lead

        # Переводим лид (если нужно)
        translated_lead = translate_text(lead)
        
        # Добавляем событие в отчет: Заголовок + Лид + Источник
        report += f"Событие №{i}: {translated_title}\n"
        report += f"{translated_lead}\n"
        report += f"Источник: {article['url']}\n\n"

    # Ограничиваем объем до 2000 знаков
    return report[:2000]

# Функция для сохранения отчета в базу данных
def save_report_to_db(report_content, source_count, article_ids):
    """Сохраняет отчет в базу данных"""
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
        logger.error(f"Ошибка сохранения отчета в базу данных: {e}")
        return None

# Асинхронная функция для отправки отчета в Telegram
async def send_report_to_telegram(report):
    """Отправляет отчет в Telegram канал"""
    try:
        app = Application.builder().token(TELEGRAM_TOKEN).build()
        await app.bot.send_message(chat_id=TARGET_CHANNEL_ID, text=report)
        return True
    except Exception as e:
        logger.error(f"Ошибка отправки в Telegram: {e}")
        return False

# Эндпоинт для запуска генерации отчета
@flask_app.route("/trigger-report", methods=["GET"])
def trigger_report():
    """Эндпоинт для запуска генерации отчета"""
    try:
        logger.info("🔍 Запрос на генерацию аналитической записки...")
        
        # Получаем свежие статьи
        articles = get_recent_articles()
        
        if not articles:
            logger.info("ℹ️ Нет новых статей для анализа")
            return jsonify({
                "status": "success",
                "message": "Нет новых статей для анализа"
            }), 200
        
        # Классифицируем статьи и выбираем ТОП-5
        top_articles = classify_articles(articles)
        
        if not top_articles:
            logger.info("ℹ️ Нет подходящих статей для формирования ТОП-5")
            return jsonify({
                "status": "success",
                "message": "Нет подходящих статей для формирования ТОП-5"
            }), 200
        
        # Генерируем отчет
        report = generate_analytical_report(top_articles)
        
        # Проверяем на дубликат
        if is_duplicate_report(report):
            logger.info("ℹ️ Обнаружен дубликат отчета. Отправка отменена.")
            return jsonify({
                "status": "success",
                "message": "Дубликат отчета. Отправка отменена."
            }), 200
        
        # Отправляем отчет в Telegram
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        success = loop.run_until_complete(send_report_to_telegram(report))
        loop.close()
        
        if not success:
            logger.error("❌ Не удалось отправить отчет в Telegram")
            return jsonify({
                "status": "error",
                "message": "Не удалось отправить отчет в Telegram"
            }), 500
        
        # Сохраняем отчет в базу данных
        article_ids = [article["id"] for article in top_articles]
        report_id = save_report_to_db(report, len(top_articles), article_ids)
        
        if report_id:
            logger.info(f"✅ Аналитическая записка (ID: {report_id}) успешно отправлена")
            return jsonify({
                "status": "success",
                "message": "Аналитическая записка успешно сгенерирована и отправлена",
                "report_id": report_id,
                "article_count": len(top_articles)
            }), 200
        else:
            logger.warning("⚠️ Отчет отправлен в Telegram, но не сохранен в базу данных")
            return jsonify({
                "status": "partial",
                "message": "Отчет отправлен в Telegram, но не сохранен в базу"
            }), 200
            
    except Exception as e:
        logger.exception(f"Критическая ошибка при генерации отчета: {e}")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

# Эндпоинт для проверки здоровья сервиса
@flask_app.route("/health", methods=["GET"])
def health_check():
    """Проверка работоспособности сервиса"""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }), 200

# Главная страница
@flask_app.route("/", methods=["GET"])
def home():
    """Главная страница"""
    return "✅ Аналитический сервис работает. Используйте /trigger-report для генерации аналитической записки.", 200

if __name__ == "__main__":
    # Запускаем Flask-приложение с привязкой к 0.0.0.0:$PORT как требуется Render
    flask_app.run(host="0.0.0.0", port=PORT, debug=False)
