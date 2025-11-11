from telegram.ext import Application, MessageHandler, filters
from db import get_supabase_client
from config import TELEGRAM_BOT_TOKEN, SOURCE_CHANNEL_ID

async def handle_message(update, context):
    message = update.message
    if message.chat.id != SOURCE_CHANNEL_ID:
        return

    # Сохраняем пост в Supabase
    client = get_supabase_client()
    data = {
        "source_url": message.link or f"https://t.me/c/{message.chat.id}/{message.message_id}",
        "title": message.text[:255] if message.text else "",
        "content": message.text or "",
        "pub_date": message.date.isoformat(),
        "channel_id": message.chat.id,
        "language": "ru",  # можно улучшить через NLP
        "keywords_matched": [],  # пока пусто
        "is_analyzed": False
    }
    client.table("ingested_content_items").insert(data).execute()

    print(f"Сохранён пост: {data['source_url']}")

def main():
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    application.add_handler(MessageHandler(filters.ALL, handle_message))

    print("Бот запущен...")
    application.run_polling()

if __name__ == "__main__":
    main()
