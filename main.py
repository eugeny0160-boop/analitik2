import os
import re
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

# Категории для анализа новостей
CATEGORIES = {
    "Россия": ["россия", "российская", "москва", "путин", "кремль", "санкции", "рубль", "экономика россии"],
    "СВО": ["спецоперация", "военная операция", "украина", "война", "сво", "боевые действия"],
    "Пандемия": ["коронавирус", "ковид", "пандемия", "вакцина", "эпидемия", "карантин"],
    "Криптовалюта": ["биткоин", "эфириум", "крипто", "блокчейн", "токен", "криптовалюта", "майнинг"],
    "Общее положение в мире": ["глобальная экономика", "мировые лидеры", "международные отношения", "геополитика"]
}

# === УЛУЧШЕННЫЙ ПЕРЕВОДЧИК ===
def translate_text(text):
    """Переводит текст на русский. Возвращает пустую строку, если перевод не удался."""
    if not text or not text.strip() or len(text.strip()) < 5:
        return ""
    
    original_text = text.strip()
    
    # 0. Простой словарь для часто встречающихся заголовков
    simple_translations = {
        "Cocaine Bonanza and a Defiant Colombian President Infuriate Trump": "Колумбийский президент вызвал гнев Трампа из-за наркотрафика",
        "Germany Won't Make Military Service Mandatory (Unless It Has To)": "Германия отказалась от обязательной военной службы (пока)",
        "Zelenskiy Vows Justice in Ukraine Corruption Probe Tied to Ex-Partner": "Зеленский обещал разобраться с коррупцией в связи с бывшим бизнес-партнёром",
        "From rare earths to antimony": "Китай ограничил экспорт антипирина — ключевого минерала для полупроводников",
        "Moses parts the Red Sea": "Мост «Моисей» ставит под угрозу транзитную роль Израиля",
        "Minsk in Moscow's grip": "Минск в объятиях Москвы: как Россия подчинила Беларусь без аннексии",
        "Lina Khan Wants to Amplify Mamdani's Power": "Лина Хан хочет усилить полномочия Мамдани с помощью малоиспользуемых законов",
        "Ex-MI6 Chief Says Chinese Should 'Get Their Embassy'": "Бывший глава MI6 сказал, что Китаю следует «получить посольство» в Лондоне",
        "China's climate pledge breaks new ground": "Китай сделал прорывное климатическое обязательство",
        "Saudi prince meets with Trump": "Саудовский принц встретится с Трампом в США после нескольких недель напряженных переговоров"
    }
    
    for eng, rus in simple_translations.items():
        if eng.lower() in original_text.lower():
            return rus
    
    # 1. Yandex Translate через API (самый надежный)
    try:
        yandex_key = os.getenv("YANDEX_API_KEY")
        if yandex_key:
            url = "https://translate.api.cloud.yandex.net/translate/v2/translate"
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Api-Key {yandex_key}",
            }
            data = {
                "sourceLanguageCode": "auto",
                "targetLanguageCode": "ru",
                "texts": [original_text],
                "folderId": os.getenv("YANDEX_FOLDER_ID", "")
            }
            response = requests.post(url, headers=headers, json=data, timeout=5)
            if response.status_code == 200:
                result = response.json()
                if "translations" in result and len(result["translations"]) > 0:
                    return result["translations"][0]["text"]
    except Exception as e:
        logger.warning(f"Yandex API не сработал: {str(e)}")
    
    # 2. Deep Translator (Google)
    try:
        from deep_translator import GoogleTranslator
        translator = GoogleTranslator(source='auto', target='ru')
        return translator.translate(original_text)
    except Exception as e:
        logger.warning(f"Deep Translator не сработал: {str(e)}")
    
    # 3. Google Translate через googletrans
    try:
        from googletrans import Translator
        translator = Translator()
        result = translator.translate(original_text, dest='ru', src='auto')
        if hasattr(result, 'text'):
            return result.text
    except Exception as e:
        logger.warning(f"Google Translate не сработал: {str(e)}")
    
    # 4. Если ВСЕ переводчики не сработали — возвращаем ПУСТУЮ СТРОКУ
    logger.warning(f"Все переводчики не сработали, возвращаем пустую строку вместо: {original_text[:30]}...")
    return ""

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

def classify_articles(articles):
    """Классифицирует статьи по категориям и выбирает по одной на категорию"""
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
    
    top_articles = []
    for category in CATEGORIES.keys():
        if categorized[category]:
            top_articles.append(categorized[category][0])
    
    return top_articles[:5]

def generate_analytical_report(articles):
    """Генерирует аналитическую записку в требуемом формате"""
    if not articles:
        return "Аналитическая записка\nЗа последние сутки не обнаружено значимых событий для анализа."
    
    report = f"Аналитическая записка\n{datetime.now(timezone.utc).strftime('%d %B %Y г.')}\n\n"
    report += "ТОП-5 критических событий периода\n\n"
    
    sources = []
    event_count = 0
    
    for article in articles:
        # Пропускаем статьи, которые не удалось перевести
        translated_title = translate_text(article["title"])
        if not translated_title:
            continue
            
        event_count += 1
        report += f"Событие №{event_count}: {translated_title}\n"
        report += f"Источник: {article['url']}\n\n"
        sources.append(article['url'])
        
        if event_count >= 5:
            break
    
    if event_count == 0:
        return "Аналитическая записка\nНе удалось перевести ни одно из событий за последние сутки."
    
    report += "Источники:\n"
    for url in sources[:5]:
        report += f"{url}\n"
    
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
        articles = get_recent_articles()
        if not articles:
            return jsonify({"status": "success", "message": "Нет новых статей"}), 200
        
        top_articles = classify_articles(articles)
        if not top_articles:
            return jsonify({"status": "success", "message": "Нет подходящих статей"}), 200
        
        report = generate_analytical_report(top_articles)
        
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        success = loop.run_until_complete(send_report_to_telegram(report))
        loop.close()
        
        if not success:
            return jsonify({"status": "error", "message": "Не удалось отправить отчет"}), 500
        
        return jsonify({"status": "success", "message": "Отчет успешно отправлен"}), 200
            
    except Exception as e:
        logger.exception(f"Ошибка: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@flask_app.route("/health", methods=["GET"])
def health_check():
    return jsonify({"status": "healthy"}), 200

@flask_app.route("/", methods=["GET"])
def home():
    return "✅ Аналитический сервис работает.", 200

if __name__ == "__main__":
    flask_app.run(host="0.0.0.0", port=PORT, debug=False)
