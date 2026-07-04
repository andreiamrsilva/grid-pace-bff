import asyncio

from openwrc.storage.data_store_service import WrcEtlService


async def main():
    etl = WrcEtlService()
    await etl.etl_historical_event(event_id=637)
    print("ETL complete.")


if __name__ == "__main__":
    asyncio.run(main())
