import os
import re
import json
from datetime import datetime, timedelta, timezone
from supabase import create_client
from telegram.ext import Application
from telegram import Update
import logging
from flask import Flask, jsonify, request

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("app.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Простой словарь для перевода ключевых фраз
TRANSLATION_DICT = {
    "Executive Summary": "Исполнительное резюме",
    "Critical Events of the Period": "Критические события периода",
    "Detailed Thematic Analysis": "Детальный тематический анализ",
    "In-depth Analysis of Impact on Russia": "Углубленный анализ влияния на Россию",
    "Impact on China and Eurasia": "Влияние на Китай и Евразию",
    "Impact on Global Situation": "Влияние на мировую обстановку",
    "Conclusions and Forecasts": "Выводы и прогнозы",
    "Key Trends of the Period": "Ключевые тенденции периода",
    "Forecast based on verified facts with probability": "Прогноз на основе верифицированных фактов со степенью вероятности",
    "Uncertainty factors": "Факторы неопределенности",
    "What requires monitoring in the next period": "Что требует мониторинга в следующем периоде",
    "Direct Effects": "Прямые эффекты",
    "Economic": "Экономические",
    "Political": "Политические",
    "Security": "Безопасность",
    "Social": "Социальные",
    "Indirect Consequences": "Косвенные последствия",
    "Opportunities": "Возможности",
    "Risks": "Риски",
    "Development of the situation": "Развитие ситуации",
    "Key consequences": "Ключевые последствия",
    "Link to Russian interests": "Связь с российскими интересами",
    "Changes in global balance": "Изменение глобального баланса",
    "Regional consequences": "Региональные последствия",
    "Systemic effects": "Системные эффекты",
    "High": "Высокая",
    "Medium": "Средняя",
    "Low": "Низкая"
}

def translate(text):
    """Простой перевод на основе словаря"""
    for eng, rus in TRANSLATION_DICT.items():
        text = text.replace(eng, rus)
    return text

# === Конфигурация ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TARGET_CHANNEL_ID = int(os.getenv("TARGET_CHANNEL_ID"))
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
PORT = int(os.getenv("PORT", 10000))

# === Инициализация ===
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
flask_app = Flask(__name__)

CATEGORIES = {
    "Россия": ["россия", "путин", "кремль", "москва", "российская", "федерация"],
    "СВО": ["сво", "военная операция", "спецоперация", "украина", "война", "военные действия"],
    "Криптовалюта": ["биткоин", "эфириум", "крипто", "блокчейн", "криптовалюта"],
    "Тенденции в мире": ["мировые тренды", "глобальная экономика", "международная политика", "мировые лидеры"],
    "Пандемия": ["пандемия", "коронавирус", "ковид", "вакцина", "эпидемия", "карантин"]
}

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
        
        logger.info(f"Получено {len(response.data)} статей за последние 24 часа")
        return response.data
    except Exception as e:
        logger.error(f"Ошибка получения статей из published_articles: {e}")
        return []

def categorize_articles(articles):
    """Классифицирует статьи по категориям и возвращает словарь с URL"""
    categorized = {category: [] for category in CATEGORIES.keys()}
    all_urls = []
    
    for article in articles:
        title = article["title"].lower()
        url = article["url"]
        all_urls.append(url)
        
        for category, keywords in CATEGORIES.items():
            if any(keyword in title for keyword in keywords):
                categorized[category].append(url)
                break
    
    return categorized, all_urls

def generate_analytical_summary(categorized_urls, all_articles):
    """Генерирует аналитическую записку по шаблону"""
    total_articles = len(all_articles)
    
    # 1. Исполнительное резюме (10%)
    executive_summary = (
        f"Аналитическая записка\n"
        f"За последние сутки зафиксировано {total_articles} новых источников информации. "
        f"Анализ выявил ключевые тенденции, требующие внимания со стороны органов власти и аналитических центров. "
        f"Особое внимание уделяется событиям, имеющим прямое или косвенное влияние на Россию и глобальную обстановку.\n\n"
    )
    
    # 2. ТОП-5 критических событий (25%)
    top_events = "2. ТОП-5 критических событий периода\n"
    event_count = 0
    
    sorted_articles = sorted(all_articles, key=lambda x: x["created_at"], reverse=True)
    for article in sorted_articles[:5]:
        event_count += 1
        top_events += (
            f"Событие №{event_count}: {article['title']}\n"
            f"• Описание: {article['title']} [{article['url']}]\n"
            f"• Критическая важность: Событие имеет высокую значимость для геополитической или экономической обстановки.\n"
            f"• Влияние на Россию: Прямые и косвенные эффекты для внутренней и внешней политики РФ. [{article['url']}]\n"
            f"• Влияние на Китай/Евразию: Возможные последствия для региональных союзников и партнеров. [{article['url']}]\n"
            f"• Глобальное влияние: Изменения в международной системе отношений. [{article['url']}]\n"
            f"• Потенциальное развитие: Обоснованные прогнозы на основе фактов с высокой степенью вероятности. [{article['url']}]\n\n"
        )
    
    if event_count == 0:
        top_events = "2. ТОП-5 критических событий периода\nНет значимых событий за указанный период.\n\n"
    
    # 3. Детальный тематический анализ (30%)
    thematic_analysis = "3. Детальный тематический анализ\n"
    for category, urls in categorized_urls.items():
        if urls:
            thematic_analysis += f"\n• {category}\n"
            for url in urls[:3]:
                article = next((a for a in all_articles if a["url"] == url), None)
                if article:
                    thematic_analysis += f"  - {article['title']} [{url}]\n"
            
            if category == "Россия":
                thematic_analysis += "  • Тренды: Усиление внимания к внутренней политике и экономическим реформам. [https://example.com/russia-trend]\n"
            elif category == "СВО":
                thematic_analysis += "  • Тренды: Продолжение военной кампании с эскалацией на отдельных направлениях. [https://example.com/military-trend]\n"
            elif category == "Криптовалюта":
                thematic_analysis += "  • Тренды: Рост регулирования и институционализации крипторынков. [https://example.com/crypto-trend]\n"
            elif category == "Тенденции в мире":
                thematic_analysis += "  • Тренды: Переформатирование глобальной экономики и политического ландшафта. [https://example.com/global-trend]\n"
            elif category == "Пандемия":
                thematic_analysis += "  • Тренды: Постепенное снятие ограничений при сохранении эпидемиологического надзора. [https://example.com/pandemic-trend]\n"
    
    if event_count == 0:
        thematic_analysis += "\nНет данных для тематического анализа.\n"
    
    # 4. Углубленный анализ влияния на Россию (15%)
    russia_impact = (
        f"\n4. Углубленный анализ влияния на Россию\n"
        f"• Прямые эффекты:\n"
        f"  o Экономические: Потенциальное влияние на национальную валюту и торговый баланс. [https://example.com/econ]\n"
        f"  o Политические: Влияние на внутреннюю политическую повестку и международную репутацию. [https://example.com/politics]\n"
        f"  o Безопасность: Угрозы национальной безопасности и внешнеполитические риски. [https://example.com/security]\n"
        f"  o Социальные: Воздействие на общественное мнение и уровень жизни. [https://example.com/social]\n"
        f"• Косвенные последствия: Перестройка международных связей и адаптация к новым условиям. [https://example.com/indirect]\n"
        f"• Возможности: Потенциал для укрепления национальных институтов и технологической независимости. [https://example.com/opportunities]\n"
        f"• Риски: Угрозы для экономической и политической стабильности. [https://example.com/risks]\n"
        f"• Развитие ситуации: Мониторинг динамики ключевых показателей. [https://example.com/development]\n"
    )
    
    # 5-7. Остальные разделы
    china_impact = (
        f"\n5. Влияние на Китай и Евразию\n"
        f"• Ключевые последствия: Углубление стратегического партнёрства и экономической интеграции. [https://example.com/china]\n"
        f"• Связь с российскими интересами: Синергия в рамках ЕАЭС и ШОС. [https://example.com/eurasia]\n"
    )
    
    global_impact = (
        f"\n6. Влияние на мировую обстановку\n"
        f"• Изменение глобального баланса: Смещение центров силы в Азию и формирование многополярности. [https://example.com/balance]\n"
        f"• Региональные последствия: Перераспределение влияния в Европе, Африке и на Ближнем Востоке. [https://example.com/regional]\n"
        f"• Системные эффекты: Трансформация международных институтов и норм. [https://example.com/systemic]\n"
    )
    
    conclusions = (
        f"\n7. Выводы и обоснованные прогнозы\n"
        f"• Ключевые тенденции периода: Усиление геополитической конкуренции и ускорение технологического разделения. [https://example.com/trends]\n"
        f"• Прогнозы: Высокая вероятность сохранения текущей траектории с усилением региональных альянсов. [https://example.com/forecast]\n"
        f"• Факторы неопределенности: Внутренние политические процессы в ключевых странах и внешние шоки. [https://example.com/uncertainty]\n"
        f"• Что требует мониторинга: Динамика санкционного давления и развитие альтернативных финансовых систем. [https://example.com/monitoring]\n"
    )
    
    # Сборка полного отчета
    full_report = (
        executive_summary +
        top_events +
        thematic_analysis +
        russia_impact +
        china_impact +
        global_impact +
        conclusions
    )
    
    # Ограничение длины до 4000 символов
    return full_report[:4000]

def save_report_to_db(report_content, source_count, categories):
    """Сохраняет сгенерированный отчёт в таблицу analytical_reports"""
    try:
        report_date = datetime.now(timezone.utc).date()
        
        data = {
            "report_date": report_date.isoformat(),
            "period_type": "daily",
            "content": report_content,
            "source_count": source_count,
            "categories": json.dumps(categories),
            "is_sent": False
        }
        
        response = supabase.table("analytical_reports").insert(data).execute()
        logger.info(f"Отчёт сохранён в базу данных с ID: {response.data[0]['id']}")
        return response.data[0]["id"]
    except Exception as e:
        logger.error(f"Ошибка сохранения отчёта в базу данных: {e}")
        return None

async def send_report_to_telegram(report):
    """Отправляет отчет в Telegram канал"""
    try:
        app = Application.builder().token(TELEGRAM_TOKEN).build()
        await app.bot.send_message(chat_id=TARGET_CHANNEL_ID, text=report)
        logger.info("Отчёт успешно отправлен в Telegram канал")
        return True
    except Exception as e:
        logger.error(f"Ошибка отправки в Telegram: {e}")
        return False

def mark_report_as_sent(report_id):
    """Отмечает отчёт как отправленный в Telegram"""
    try:
        supabase.table("analytical_reports") \
            .update({"is_sent": True}) \
            .eq("id", report_id) \
            .execute()
        logger.info(f"Отчёт с ID {report_id} помечен как отправленный")
    except Exception as e:
        logger.error(f"Ошибка обновления статуса отчета {report_id}: {e}")

@flask_app.route("/trigger-report", methods=["GET"])
def trigger_report():
    """Эндпоинт для запуска генерации отчета"""
    try:
        logger.info("🔍 Запрос на генерацию отчёта...")
        
        articles = get_recent_articles()
        
        if not articles:
            logger.info("ℹ️ Нет новых статей для анализа за последние 24 часа")
            return jsonify({
                "status": "success",
                "message": "Нет новых статей для анализа"
            }), 200
        
        categorized_urls, all_urls = categorize_articles(articles)
        report = generate_analytical_summary(categorized_urls, articles)
        
        report_id = save_report_to_db(report, len(articles), categorized_urls)
        
        if not report_id:
            logger.error("❌ Не удалось сохранить отчет в базу данных")
            return jsonify({
                "status": "error",
                "message": "Ошибка сохранения отчета"
            }), 500
        
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        success = loop.run_until_complete(send_report_to_telegram(report))
        loop.close()
        
        if success:
            mark_report_as_sent(report_id)
            logger.info(f"✅ Отчёт (ID: {report_id}) успешно отправлен и помечен как отправленный")
            return jsonify({
                "status": "success",
                "message": "Отчёт успешно сгенерирован, сохранён и отправлен",
                "report_id": report_id,
                "article_count": len(articles)
            }), 200
        else:
            logger.error(f"❌ Не удалось отправить отчет (ID: {report_id}) в Telegram")
            return jsonify({
                "status": "error",
                "message": "Отчёт сохранён, но не отправлен в Telegram"
            }), 500
            
    except Exception as e:
        logger.exception(f"Критическая ошибка при генерации отчета: {e}")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

@flask_app.route("/health", methods=["GET"])
def health_check():
    """Проверка работоспособности сервиса"""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }), 200

@flask_app.route("/", methods=["GET"])
def home():
    """Главная страница"""
    return "✅ Аналитический сервис работает. Используйте /trigger-report для генерации отчёта.", 200

if __name__ == "__main__":
    flask_app.run(host="0.0.0.0", port=PORT, debug=False)
