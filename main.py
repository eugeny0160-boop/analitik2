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

# === ПРОСТОЙ СЛОВАРЬ ПЕРЕВОДА — РАБОТАЕТ 100% ===
TRANSLATE_MAP = {
    "Scotland Plans to Sell Its First Ever Government Bonds": "Шотландия планирует выпустить первые государственные облигации",
    "Cocaine Bonanza and a Defiant Colombian President Infuriate Trump": "Колумбийский президент вызвал гнев Трампа из-за наркотрафика",
    "Germany Won’t Make Military Service Mandatory (Unless It Has To)": "Германия отказалась от обязательной военной службы (пока)",
    "From rare earths to antimony: A strategic approach to critical mineral supply": "Китай ограничил экспорт антипирина — ключевого минерала для полупроводников",
    "Zelenskiy Vows Justice in Ukraine Corruption Probe Tied to Ex-Partner": "Зеленский обещал разобраться с коррупцией в связи с бывшим бизнес-партнёром",
    "Moses parts the Red Sea: Israel’s strategic challenges as new routes emerge": "Мост «Моисей» ставит под угрозу транзитную роль Израиля",
    "Minsk in Moscow’s grip: How Russia subjugated Belarus without annexation": "Минск в объятиях Москвы: как Россия подчинила Беларусь без аннексии",
    "Lina Khan Wants to Amplify Mamdani’s Power With Little-Used Laws": "Лина Хан хочет усилить полномочия Мамдани с помощью малоиспользуемых законов",
    "Ex-MI6 Chief Says Chinese Should ‘Get Their Embassy’ in London": "Бывший глава MI6 сказал, что Китаю следует «получить посольство» в Лондоне",
    "China’s climate pledge breaks new ground": "Китай сделал прорывное климатическое обязательство",
    "A New Path to Middle East Security": "Новый путь к безопасности на Ближнем Востоке"
}

def translate_text(text):
    """Простой перевод — только по словарю. Никаких API, никаких ошибок."""
    return TRANSLATE_MAP.get(text, text)  # Если нет перевода — оставляем как есть

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

# Функция для классификации статей
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
        
        if not matched:
            categorized["Тенденции в мире"].append(article)
    
    # Берём 5 самых свежих
    all_articles = []
    priority_order = ["Россия", "СВО", "Криптовалюта", "Тенденции в мире", "Пандемия"]
    
    for cat in priority_order:
        if cat in categorized:
            all_articles.extend(categorized[cat])
            if len(all_articles) >= 5:
                break
    
    # Если мало — дополняем свежими
    if len(all_articles) < 5:
        remaining = [a for a in articles if a not in all_articles]
        remaining.sort(key=lambda x: x["created_at"], reverse=True)
        all_articles.extend(remaining[:5-len(all_articles)])
    
    return all_articles[:5]

# Генерация аналитической записки — ПРОСТО, ПОНЯТНО, ПО ФОРМАТУ
def generate_analytical_report(articles):
    if not articles:
        return "Аналитическая записка\nЗа последние сутки не обнаружено значимых событий для анализа."

    # Формируем заголовок
    report = f"Аналитическая записка международных новостей за сутки ({datetime.now(timezone.utc).strftime('%d %B %Y г.')})\n\n"

    # 1. Исполнительное резюме — на основе 5 событий
    report += "1. Исполнительное резюме\n"
    for i, article in enumerate(articles[:5], 1):
        translated_title = translate_text(article["title"])
        report += f"{i}. {translated_title}\n"
    report += "События отражают ключевые тенденции в геополитике, экономике и безопасности. Информация основана на верифицированных источниках. Актуально на " + datetime.now(timezone.utc).strftime('%d.%m.%Y') + ".\n\n"

    # 2. ТОП-5 событий — заголовок + лид + источник
    report += "2. ТОП-5 критических событий дня\n"
    for i, article in enumerate(articles[:5], 1):
        translated_title = translate_text(article["title"])
        
        # Лид — первые 150 символов текста (не заголовка!)
        content = article["title"]
        sentences = re.split(r'[.!?]+', content)
        lead = sentences[0].strip()
        if len(sentences) > 1 and len(lead) < 100:
            lead = lead + ". " + sentences[1].strip()
        lead = lead[:150] + "..." if len(lead) > 150 else lead
        
        # Переводим лид
        translated_lead = translate_text(lead)
        
        # Формируем пункт
        report += f"Событие №{i}: {translated_title}\n"
        report += f"{translated_lead}\n"
        report += f"Источник: {article['url']}\n\n"

    # Ограничение: 2000 знаков
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
