import asyncio
from api.news_service import fetch_news_from_feed

async def main():
    print("Testing WRC PT...")
    wrc_pt = await fetch_news_from_feed("wrc", "pt")
    print(f"WRC PT count: {len(wrc_pt)}")
    
    print("\nTesting F1 PT...")
    f1_pt = await fetch_news_from_feed("f1", "pt")
    print(f"F1 PT count: {len(f1_pt)}")
    
    print("\nTesting WRC EN...")
    wrc_en = await fetch_news_from_feed("wrc", "en")
    print(f"WRC EN count: {len(wrc_en)}")

if __name__ == "__main__":
    asyncio.run(main())
