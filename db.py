from supabase import create_client, Client
import os

def get_supabase_client() -> Client:
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    return create_client(url, key)

# Пример: получение непроанализированных постов
def get_unanalyzed_posts(client, days=7):
    query = (
        client.table("ingested_content_items")
        .select("*")
        .eq("is_analyzed", False)
        .gte("pub_date", f"now() - interval '{days} days'")
        .order("pub_date", desc=True)
    )
    response = query.execute()
    return response.data
