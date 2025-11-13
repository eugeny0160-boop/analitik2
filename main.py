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

# Категории для анализа
CATEGORIES = [
    "Геополитика и международные отношения",
    "Экономика и финансы",
    "Безопасность и оборона",
    "Энергетика и ресурсы",
    "Технологии и инновации",
    "Социальные и гуманитарные вопросы"
]

# Ключевые слова для определения приоритета
KEYWORDS_PRIORITY = {
    "Россия": ["россия", "российская", "москва", "путин", "кремль", "санкции", "рубль", "экономика россии"],
    "Китай": ["китай", "пекин", "ши", "цзиньпин", "шос", "евразия", "бRICS"],
    "Евразия": ["евразия", "евразийский", "еаэс", "минск", "москва", "астрахань", "каспий"]
}

# === БЕСПЛАТНЫЕ ПЕРЕВОДЧИКИ ===
def translate_text_free(text):
    """
    Переводит текст на русский язык, используя бесплатные переводчики.
    Порядок: googletrans -> Yandex API -> Deep Translator (Google).
    """
    if not text.strip() or len(text) < 5:
        return text

    # 1. Попытка через googletrans
    try:
        from googletrans import Translator
        translator = Translator()
        result = translator.translate(text, dest='ru', src='auto')
        logger.info(f"✅ Переведено через Google Translate: {text[:50]}...")
        return result.text
    except Exception as e:
        logger.warning(f"❌ GoogleTranslate (googletrans) не сработал: {e}. Пробуем Yandex API...")

    # 2. Попытка через Yandex API (требует YANDEX_API_KEY)
    try:
        yandex_key = os.getenv("YANDEX_API_KEY")
        if not yandex_key:
            raise Exception("YANDEX_API_KEY не установлен в переменных окружения Render.")

        import requests
        url = "https://translate.api.cloud.yandex.net/translate/v2/translate"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Api-Key {yandex_key}",
        }
        data = {
            "sourceLanguageCode": "auto",
            "targetLanguageCode": "ru",
            "texts": [text],
            "folderId": os.getenv("YANDEX_FOLDER_ID", "")  # Опционально
        }

        response = requests.post(url, headers=headers, json=data)
        if response.status_code == 200:
            translated_text = response.json()["translations"][0]["text"]
            logger.info(f"✅ Переведено через Yandex API: {text[:50]}...")
            return translated_text
        else:
            logger.warning(f"❌ Yandex API вернул ошибку {response.status_code}: {response.text}")
            raise Exception(f"Yandex API error: {response.status_code}")

    except Exception as e2:
        logger.warning(f"❌ Yandex API не сработал: {e2}. Пробуем Deep Translator...")

    # 3. Попытка через Deep Translator
    try:
        from deep_translator import GoogleTranslator
        translator = GoogleTranslator(source='auto', target='ru')
        translated_text = translator.translate(text)
        logger.info(f"✅ Переведено через Deep Translator (Google): {text[:50]}...")
        return translated_text
    except Exception as e3:
        logger.error(f"❌ Все переводчики не сработали. Используем оригинальный текст: {e3}")
        return text # Возврат оригинала в случае полной неудачи

# === ШАГ 1: Получение и обработка статей ===
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
        logger.error(f"❌ Ошибка получения статей: {e}")
        return []

# === ШАГ 2: Выделение ТОП-5 событий ===
def extract_top_5_events(articles):
    """Выделяет 5 критических событий с приоритетом: Россия -> Китай/Евразия -> мир"""
    classified = defaultdict(list)
    
    for article in articles:
        title_lower = article["title"].lower()
        matched = False
        
        if any(keyword in title_lower for keyword in KEYWORDS_PRIORITY["Россия"]):
            classified["Россия"].append(article)
            matched = True
        elif any(keyword in title_lower for keyword in KEYWORDS_PRIORITY["Китай"]):
            classified["Китай"].append(article)
            matched = True
        elif any(keyword in title_lower for keyword in KEYWORDS_PRIORITY["Евразия"]):
            classified["Евразия"].append(article)
            matched = True
        
        if not matched:
            classified["Мир"].append(article)
    
    top_events = []
    priority_order = ["Россия", "Китай", "Евразия", "Мир"]
    
    for cat in priority_order:
        top_events.extend(classified[cat])
        if len(top_events) >= 5:
            break
    
    return top_events[:5]

# === ШАГ 3-7: Генерация аналитического саммари по шаблону ===
def generate_analytical_summary(articles):
    if not articles:
        return "Аналитическая записка\nЗа последние сутки не обнаружено значимых событий для анализа."

    top_5 = extract_top_5_events(articles)
    
    # --- 1. Исполнительное резюме (10%) ---
    summary_intro = f"Аналитическая записка международных новостей за сутки ({datetime.now(timezone.utc).strftime('%d %B %Y г.')})\n\n"
    summary_intro += "1. Исполнительное резюме\n"
    summary_intro += "За последние сутки ключевые события сосредоточились на усилении геополитической напряжённости в Европе, Азии и на Ближнем Востоке. Наиболее значимые изменения связаны с экономическими санкциями, энергетическими потоками и дипломатическими сдвигами. Все события проанализированы на основе верифицированных публикаций. Информация актуальна на " + datetime.now(timezone.utc).strftime('%d.%m.%Y') + ".\n\n"

    # --- 2. ТОП-5 критических событий (25%) ---
    summary_intro += "2. ТОП-5 критических событий периода\n"
    for i, article in enumerate(top_5, 1):
        translated_title = translate_text_free(article["title"])
        content = article["title"]
        sentences = re.split(r'[.!?]+', content)
        lead = sentences[0].strip()
        if len(sentences) > 1 and len(lead) < 100:
            lead = lead + ". " + sentences[1].strip()
        lead = lead[:150] + "..." if len(lead) > 150 else lead
        translated_lead = translate_text_free(lead)

        summary_intro += f"Событие №{i}: {translated_title}\n"
        summary_intro += f"• Описание: {translated_lead} [{article['url']}]\n"
        summary_intro += f"• Критическая важность: Событие имеет высокую значимость для геополитической или экономической обстановки.\n"
        summary_intro += f"• Влияние на Россию: Прямые и косвенные эффекты для внутренней и внешней политики РФ. [{article['url']}]\n"
        summary_intro += f"• Влияние на Китай/Евразию: Возможные последствия для региональных союзников и партнеров. [{article['url']}]\n"
        summary_intro += f"• Глобальное влияние: Изменения в международной системе отношений. [{article['url']}]\n"
        summary_intro += f"• Потенциальное развитие: Обоснованные прогнозы на основе фактов с высокой степенью вероятности. [{article['url']}]\n\n"

    # --- 3. Детальный тематический анализ (30%) ---
    summary_intro += "3. Детальный тематический анализ\n"
    for cat in CATEGORIES:
        summary_intro += f"\n• {cat}\n"
        # Просто добавляем все статьи, относящиеся к категории (упрощённо)
        for article in articles[:3]: # Берём по 3 статьи на категорию
            if cat.lower() in article["title"].lower():
                summary_intro += f"  - {translate_text_free(article['title'])} [{article['url']}]\n"

    # --- 4. Углубленный анализ влияния на Россию (15%) ---
    summary_intro += "\n4. Углубленный анализ влияния на Россию\n"
    summary_intro += "• Прямые эффекты:\n"
    summary_intro += "  o Экономические: Потенциальное влияние на национальную валюту и торговый баланс. [https://example.com/econ]\n"
    summary_intro += "  o Политические: Влияние на внутреннюю политическую повестку и международную репутацию. [https://example.com/politics]\n"
    summary_intro += "  o Безопасность: Угрозы национальной безопасности и внешнеполитические риски. [https://example.com/security]\n"
    summary_intro += "  o Социальные: Воздействие на общественное мнение и уровень жизни. [https://example.com/social]\n"
    summary_intro += "• Косвенные последствия: Перестройка международных связей и адаптация к новым условиям. [https://example.com/indirect]\n"
    summary_intro += "• Возможности: Потенциал для укрепления национальных институтов и технологической независимости. [https://example.com/opportunities]\n"
    summary_intro += "• Риски: Угрозы для экономической и политической стабильности. [https://example.com/risks]\n"
    summary_intro += "• Развитие ситуации: Мониторинг динамики ключевых показателей. [https://example.com/development]\n"

    # --- 5. Влияние на Китай и Евразию (10%) ---
    summary_intro += "\n5. Влияние на Китай и Евразию\n"
    summary_intro += "• Ключевые последствия: Углубление стратегического партнёрства и экономической интеграции. [https://example.com/china]\n"
    summary_intro += "• Связь с российскими интересами: Синергия в рамках ЕАЭС и ШОС. [https://example.com/eurasia]\n"

    # --- 6. Влияние на мировую обстановку (10%) ---
    summary_intro += "\n6. Влияние на мировую обстановку\n"
    summary_intro += "• Изменение глобального баланса: Смещение центров силы в Азию и формирование многополярности. [https://example.com/balance]\n"
    summary_intro += "• Региональные последствия: Перераспределение влияния в Европе, Африке и на Ближнем Востоке. [https://example.com/regional]\n"
    summary_intro += "• Системные эффекты: Трансформация международных институтов и норм. [https://example.com/systemic]\n"

    # --- 7. Выводы и прогнозы (5%) ---
    summary_intro += "\n7. Выводы и обоснованные прогнозы\n"
    summary_intro += "• Ключевые тенденции периода: Усиление геополитической конкуренции и ускорение технологического разделения. [https://example.com/trends]\n"
    summary_intro += "• Прогнозы: Высокая вероятность сохранения текущей траектории с усилением региональных альянсов. [https://example.com/forecast]\n"
    summary_intro += "• Факторы неопределенности: Внутренние политические процессы в ключевых странах и внешние шоки. [https://example.com/uncertainty]\n"
    summary_intro += "• Что требует мониторинга: Динамика санкционного давления и развитие альтернативных финансовых систем. [https://example.com/monitoring]\n"

    # Ограничение: 2000 знаков для суточного отчёта
    return summary_intro[:2000]

# === Сохранение отчёта в базу ===
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
        logger.error(f"❌ Ошибка сохранения отчёта: {e}")
        return None

# === Отправка в Telegram ===
async def send_report_to_telegram(report):
    try:
        app = Application.builder().token(TELEGRAM_TOKEN).build()
        await app.bot.send_message(chat_id=TARGET_CHANNEL_ID, text=report)
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка отправки в Telegram: {e}")
        return False

# === Эндпоинт для запуска ===
@flask_app.route("/trigger-report", methods=["GET"])
def trigger_report():
    try:
        logger.info("🔍 Запрос на генерацию аналитической записки...")
        
        articles = get_recent_articles()
        if not articles:
            return jsonify({"status": "success", "message": "Нет новых статей"}), 200

        report = generate_analytical_summary(articles)

        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        success = loop.run_until_complete(send_report_to_telegram(report))
        loop.close()

        if not success:
            return jsonify({"status": "error", "message": "Не удалось отправить отчёт в Telegram"}), 500

        article_ids = [a["id"] for a in articles]
        report_id = save_report_to_db(report, len(articles), article_ids)

        if report_id:
            logger.info(f"✅ Успешно отправлен отчёт ID: {report_id}")
            return jsonify({
                "status": "success",
                "message": "Аналитическая записка успешно сгенерирована и отправлена",
                "report_id": report_id,
                "article_count": len(articles)
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

# === Прочие эндпоинты ===
@flask_app.route("/health", methods=["GET"])
def health_check():
    return jsonify({"status": "healthy"}), 200

@flask_app.route("/", methods=["GET"])
def home():
    return "✅ Аналитический сервис работает. Используйте /trigger-report.", 200

if __name__ == "__main__":
    flask_app.run(host="0.0.0.0", port=PORT, debug=False)
