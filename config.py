import os
from dotenv import load_dotenv

load_dotenv()

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
SOURCE_CHANNEL_ID = int(os.getenv("SOURCE_CHANNEL_ID"))
TARGET_CHANNELS = [int(ch) for ch in os.getenv("TARGET_CHANNELS", "").split(",")]

# Supabase
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Периоды для отчётов
REPORT_PERIODS = {
    "daily": {"cron": "0 18 * * *", "chars": 1500},
    "weekly": {"cron": "0 18 * * 0", "chars": 3000},
    "monthly": {"cron": "0 18 1 * *", "chars": 6000},
    "semiannual": {"cron": "0 18 1 1,7 *", "chars": 9000},
    "annual": {"cron": "0 18 1 1 *", "chars": 10000}
}

# Языки и ключевые слова
RUSSIA_KEYWORDS = [
    "Россия", "Russia", "российск", "russo", "russe", "rusia", "russland",
    "Москва", "Putin", "Кремль", "Путин", "МИД", "ФСБ", "СВО", "Украина"
]
