import asyncio
import logging
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram.ext import Application
from analyzer import generate_analytical_report
from config import TARGET_CHANNELS, REPORT_PERIODS, TELEGRAM_BOT_TOKEN
from db import get_supabase_client


# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("scheduler.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


async def send_report_to_channels(report_text: str, period_type: str):
    """
    Отправляет сгенерированный отчёт в целевые Telegram-каналы.
    """
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    for channel_id in TARGET_CHANNELS:
        try:
            # Отправка текста как есть, если он укладывается в лимит
            if len(report_text) <= 4096:
                await app.bot.send_message(chat_id=channel_id, text=report_text, parse_mode="HTML")
            else:
                # Если текст длинный — отправляем как файл
                from io import StringIO
                import aiofiles
                from pathlib import Path

                # Создаём временный файл с отчётом
                temp_file = f"report_{period_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
                async with aiofiles.open(temp_file, "w", encoding="utf-8") as f:
                    await f.write(report_text)

                # Отправляем файл
                await app.bot.send_document(chat_id=channel_id, document=open(temp_file, "rb"))

                # Удаляем временный файл
                Path(temp_file).unlink(missing_ok=True)

            logger.info(f"Отчёт {period_type} отправлен в канал {channel_id}")
        except Exception as e:
            logger.error(f"Ошибка при отправке в канал {channel_id}: {e}")


async def schedule_daily_report():
    """
    Задача: ежедневный отчёт.
    """
    logger.info("Запуск ежедневной генерации отчёта...")
    report = generate_analytical_report("daily")
    await send_report_to_channels(report, "daily")


async def schedule_weekly_report():
    """
    Задача: еженедельный отчёт.
    """
    logger.info("Запуск еженедельной генерации отчёта...")
    report = generate_analytical_report("weekly")
    await send_report_to_channels(report, "weekly")


async def schedule_monthly_report():
    """
    Задача: ежемесячный отчёт.
    """
    logger.info("Запуск ежемесячной генерации отчёта...")
    report = generate_analytical_report("monthly")
    await send_report_to_channels(report, "monthly")


async def schedule_semiannual_report():
    """
    Задача: полугодовой отчёт.
    """
    logger.info("Запуск полугодовой генерации отчёта...")
    report = generate_analytical_report("semiannual")
    await send_report_to_channels(report, "semiannual")


async def schedule_annual_report():
    """
    Задача: годовой отчёт.
    """
    logger.info("Запуск годовой генерации отчёта...")
    report = generate_analytical_report("annual")
    await send_report_to_channels(report, "annual")


def start_scheduler():
    """
    Запускает планировщик задач.
    """
    scheduler = AsyncIOScheduler()

    # Добавляем задачи по расписанию
    scheduler.add_job(schedule_daily_report, "cron", hour=18, minute=0, timezone="UTC", id="daily_report")
    scheduler.add_job(schedule_weekly_report, "cron", day_of_week="sun", hour=18, minute=0, timezone="UTC", id="weekly_report")
    scheduler.add_job(schedule_monthly_report, "cron", day=1, hour=18, minute=0, timezone="UTC", id="monthly_report")
    scheduler.add_job(schedule_semiannual_report, "cron", month="1,7", day=1, hour=18, minute=0, timezone="UTC", id="semiannual_report")
    scheduler.add_job(schedule_annual_report, "cron", month=1, day=1, hour=18, minute=0, timezone="UTC", id="annual_report")

    scheduler.start()
    logger.info("Планировщик запущен.")

    # Запускаем асинхронный цикл
    try:
        asyncio.get_event_loop().run_forever()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Планировщик остановлен.")
        scheduler.shutdown()


if __name__ == "__main__":
    start_scheduler()
