# 🤖 Финансист-Аналитик — Telegram-бот для анализа новостей (с Gunicorn)

## Что делает бот?

- Читает **все посты** из приватного Telegram-канала.
- Сохраняет их в **Supabase** (без дубликатов).
- Генерирует **ежедневную аналитическую записку** по источникам за последние 24 часа.
- Отправляет отчёт в публичный канал.
- Работает как **Web Service** на Render с **Gunicorn**.

---

## ✅ Как настроить

### 1. Создайте таблицу в Supabase

```sql
CREATE TABLE ingested_content_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_url TEXT UNIQUE NOT NULL,
    title TEXT,
    content TEXT,
    pub_date TIMESTAMPTZ,
    channel_id BIGINT,
    language TEXT,
    is_analyzed BOOLEAN DEFAULT false
);
