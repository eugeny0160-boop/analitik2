# Analitik2 — Автоматизированный аналитический бот для Telegram

## Описание

Бот анализирует посты из Telegram-канала, фильтрует по ключевым словам (особенно связанным с Россией), верифицирует факты, генерирует отчёты по расписанию и отправляет их в целевые каналы.

## Требования

- Python 3.11+
- Аккаунт на [Render](https://render.com)
- Проект на [Supabase](https://supabase.com)
- Токен Telegram Bot

## Установка

1. Клонируйте репозиторий
2. Установите зависимости: `pip install -r requirements.txt`
3. Создайте `.env` файл (см. пример ниже)
4. Запустите: `python bot.py`

## Переменные окружения (.env)

```env
TELEGRAM_BOT_TOKEN=ваш_токен
SOURCE_CHANNEL_ID=-100xxxxxx
TARGET_CHANNELS=-100yyyyyy,-100zzzzzz
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=ваш_anon_key
