import os
import re
from datetime import datetime, timedelta, timezone
from supabase import create_client
from telegram.ext import Application
from flask import Flask, jsonify, request
import logging

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

# Категории для анализа новостей
CATEGORIES = {
    "Россия": ["россия", "российская", "москва", "путин", "кремль", "санкции", "рубль", "экономика россии"],
    "СВО": ["спецоперация", "военная операция", "украина", "война", "сво", "боевые действия"],
    "Пандемия": ["коронавирус", "ковид", "пандемия", "вакцина", "эпидемия", "карантин"],
    "Криптовалюта": ["биткоин", "эфириум", "крипто", "блокчейн", "токен", "криптовалюта", "майнинг"],
    "Общее положение в мире": ["глобальная экономика", "мировые лидеры", "международные отношения", "геополитика"]
}

def simple_translate(text):
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

def classify_articles(articles):
    """Классифицирует статьи по категориям и определяет наиболее важные для каждой категории"""
    categorized = {category: [] for category in CATEGORIES.keys()}
    
    for article in articles:
        title_lower = article["title"].lower()
        matched = False
        
        for category, keywords in CATEGORIES.items():
            if any(keyword in title_lower for keyword in keywords):
                categorized[category].append(article)
                matched = True
                break
        
        if not matched:
            categorized["Общее положение в мире"].append(article)
    
    # Выбираем по одной наиболее релевантной статье из каждой категории
    top_articles = []
    for category in CATEGORIES.keys():
        if categorized[category]:
            top_articles.append(categorized[category][0])
    
    # Если меньше 5 статей, дополняем последними новостями
    if len(top_articles) < 5:
        remaining = [a for a in articles if a not in top_articles]
        top_articles.extend(remaining[:5-len(top_articles)])
    
    return top_articles[:5]

def generate_analytical_report(articles):
    """Генерирует аналитическую записку в требуемом формате"""
    if not articles:
        return "Аналитическая записка\nЗа последние сутки не обнаружено значимых событий для анализа."
    
    # Формируем заголовок
    report = f"Аналитическая записка\n{datetime.now(timezone.utc).strftime('%d %B %Y г.')}\n\n"
    
    # ТОП-5 критических событий
    report += "ТОП-5 критических событий периода\n\n"
    
    # Список ссылок для последнего раздела
    sources = []
    
    # Для каждой категории берем по одной статье
    for i, article in enumerate(articles[:5], 1):
        category = None
        title_lower = article["title"].lower()
        
        # Определяем категорию статьи
        for cat, keywords in CATEGORIES.items():
            if any(keyword in title_lower for keyword in keywords):
                category = cat
                break
        if not category:
            category = "Общее положение в мире"
        
        # Формируем событие
        translated_title = simple_translate(article["title"])
        report += f"Событие №{i}: {translated_title}\n"
        report += f"Источник: {article['url']}\n\n"
        sources.append(article['url'])
    
    # Добавляем раздел с источниками
    report += "Источники:\n"
    for url in sources[:5]:  # Максимум 5 уникальных источников
        report += f"{url}\n"
    
    # Ограничиваем объем до 2000 знаков
    return report[:2000]

async def send_report_to_telegram(report):
    """Отправляет отчет в Telegram канал"""
    try:
        app = Application.builder().token(TELEGRAM_TOKEN).build()
        await app.bot.send_message(chat_id=TARGET_CHANNEL_ID, text=report)
        return True
    except Exception as e:
        logger.error(f"Ошибка отправки в Telegram: {e}")
        return False

@flask_app.route("/trigger-report", methods=["GET"])
def trigger_report():
    """Эндпоинт для запуска генерации отчета"""
    try:
        logger.info("Запрос на генерацию аналитической записки...")
        
        # Получаем свежие статьи
        articles = get_recent_articles()
        
        if not articles:
            logger.info("Нет новых статей для анализа")
            return jsonify({
                "status": "success",
                "message": "Нет новых статей для анализа"
            }), 200
        
        # Классифицируем статьи по категориям
        top_articles = classify_articles(articles)
        
        if not top_articles:
            logger.info("Нет подходящих статей для формирования ТОП-5")
            return jsonify({
                "status": "success",
                "message": "Нет подходящих статей для формирования ТОП-5"
            }), 200
        
        # Генерируем отчет
        report = generate_analytical_report(top_articles)
        
        # Отправляем отчет в Telegram
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        success = loop.run_until_complete(send_report_to_telegram(report))
        loop.close()
        
        if not success:
            logger.error("Не удалось отправить отчет в Telegram")
            return jsonify({
                "status": "error",
                "message": "Не удалось отправить отчет в Telegram"
            }), 500
        
        logger.info("Отчет успешно отправлен")
        return jsonify({
            "status": "success",
            "message": "Аналитическая записка успешно сгенерирована и отправлена"
        }), 200
            
    except Exception as e:
        logger.exception(f"Критическая ошибка при генерации отчета: {e}")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

@flask_app.route("/health", methods=["GET"])
def health_check():
    """Проверка работоспособности сервиса"""
    return jsonify({"status": "healthy"}), 200

@flask_app.route("/", methods=["GET"])
def home():
    """Главная страница"""
    return "✅ Аналитический сервис работает. Используйте /trigger-report для генерации аналитической записки.", 200

if __name__ == "__main__":
    flask_app.run(host="0.0.0.0", port=PORT, debug=False)
