import asyncio
import logging
from datetime import datetime, date, timezone
import json

from core.database_service import init_db, upsert_events, save_stages_to_db
from core.redis_service import set_cached_data, get_cached_data
from models.calendar import CalendarEvent
from models.event import Stage
from models.stage_times import StageStandings, DriverTime
from ingestion.agent_analyst import WRCAnalystAgent

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

async def run_simulator():
    await init_db()
    
    EVENT_ID = 999
    STAGE_ID = 9991
    CATEGORY = "WRC"
    
    logger.info("🔧 Preparing Mock Data in DB...")
    # 1. Create a mock event
    mock_event = CalendarEvent(
        id=EVENT_ID,
        name="WRC Rally Simulator 2026",
        category=CATEGORY,
        country="Portugal",
        start_date=date.today(),
        finish_date=date.today(),
        status="Running"
    )
    await upsert_events([mock_event])
    
    # 2. Create a mock stage
    mock_stage = Stage(
        id=STAGE_ID,
        name="SS1 - Test Stage",
        number=1,
        distance=15.5,
        start_time=datetime.now(timezone.utc),
        status="Running",
        is_live=True
    )
    await save_stages_to_db(EVENT_ID, [mock_stage])
    
    # Also save stages to redis so the API fetches it immediately
    await set_cached_data(f"event:wrc:{EVENT_ID}:stages", [mock_stage.model_dump(mode='json')], 3600)
    
    logger.info(f"✅ Mock Data Ready. Event ID: {EVENT_ID}, Stage ID: {STAGE_ID}.")
    logger.info(f"📱 You can now open your app and check the stages for Event {EVENT_ID}.")
    logger.info("⏱️ Starting Live Timing Sequence in 5 seconds...")
    await asyncio.sleep(5)
    
    redis_times_key = f"live:times:wrc:{STAGE_ID}"
    redis_timeline_key = f"timeline:wrc:{STAGE_ID}"
    
    # Clear old simulator data if any
    await set_cached_data(redis_timeline_key, [], 1) # expire
    await set_cached_data(redis_times_key, None, 1) # expire
    await asyncio.sleep(1) # wait for clear
    
    def create_standings(drivers, last_updated):
        return StageStandings(
            stage_id=STAGE_ID,
            event_id=EVENT_ID,
            category=CATEGORY,
            is_live=True,
            last_updated=last_updated,
            standings=drivers
        )
    
    # TICK 1: Neuville Starts
    dt1 = datetime.now(timezone.utc)
    s1 = create_standings([
        DriverTime(entry_id=11, driver_name="Thierry Neuville", status="OnTrack", position=1, time=None, diff_to_first=None)
    ], dt1)
    
    # TICK 2: Ogier Starts
    dt2 = datetime.now(timezone.utc)
    s2 = create_standings([
        DriverTime(entry_id=11, driver_name="Thierry Neuville", status="OnTrack", position=1, time=None, diff_to_first=None),
        DriverTime(entry_id=17, driver_name="Sebastien Ogier", status="OnTrack", position=2, time=None, diff_to_first=None)
    ], dt2)
    
    # TICK 3: Neuville finishes, Ogier loses positions (simulated error)
    dt3 = datetime.now(timezone.utc)
    s3 = create_standings([
        DriverTime(entry_id=11, driver_name="Thierry Neuville", status="Finished", position=1, time="10:45.3", diff_to_first=None),
        DriverTime(entry_id=33, driver_name="Elfyn Evans", status="OnTrack", position=2, time=None, diff_to_first=None),
        DriverTime(entry_id=69, driver_name="Kalle Rovanpera", status="OnTrack", position=3, time=None, diff_to_first=None),
        DriverTime(entry_id=8, driver_name="Ott Tanak", status="OnTrack", position=4, time=None, diff_to_first=None),
        DriverTime(entry_id=17, driver_name="Sebastien Ogier", status="OnTrack", position=5, time=None, diff_to_first=None)
    ], dt3)
    
    # TICK 4: Ogier retires
    dt4 = datetime.now(timezone.utc)
    s4 = create_standings([
        DriverTime(entry_id=11, driver_name="Thierry Neuville", status="Finished", position=1, time="10:45.3", diff_to_first=None),
        DriverTime(entry_id=33, driver_name="Elfyn Evans", status="OnTrack", position=2, time=None, diff_to_first=None),
        DriverTime(entry_id=69, driver_name="Kalle Rovanpera", status="OnTrack", position=3, time=None, diff_to_first=None),
        DriverTime(entry_id=8, driver_name="Ott Tanak", status="OnTrack", position=4, time=None, diff_to_first=None),
        DriverTime(entry_id=17, driver_name="Sebastien Ogier", status="Retired", position=None, time=None, diff_to_first=None)
    ], dt4)
    
    ticks = [s1, s2, s3, s4]
    
    for i, tick_standings in enumerate(ticks):
        logger.info(f"\n--- TICK {i+1} ---")
        
        old_data = await get_cached_data(redis_times_key)
        
        # 1. Calculate events
        if old_data:
            old_standings = StageStandings(**old_data)
            new_events = WRCAnalystAgent.analyze_wrc_timings(old_standings, tick_standings)
            
            if new_events:
                logger.info(f"🚨 Agent 03 inferred {len(new_events)} new events!")
                for ev in new_events:
                    logger.info(f"   💬 [{ev.severity}] {ev.message}")
                    
                existing_events_raw = await get_cached_data(redis_timeline_key) or []
                existing_events_raw.extend([e.model_dump(mode='json') for e in new_events])
                await set_cached_data(redis_timeline_key, existing_events_raw, expiration_seconds=3600)
        else:
            logger.info("Initial state, simulating first entries (without previous to compare)...")
            # For the very first tick, we manually generate the start events since old_data is None
            manual_events = []
            for d in tick_standings.standings:
                 if d.status == "OnTrack":
                     manual_events.append(
                         TimelineEvent(
                             id=str(uuid.uuid4()),
                             timestamp=tick_standings.last_updated,
                             source=TimelineEventSource.WRC_SYSTEM_INFERENCE,
                             severity=TimelineEventSeverity.INFO,
                             message=f"🟢 {d.driver_name} iniciou a Especial.",
                             driver_name=d.driver_name,
                             metadata={
                                 "message_pt": f"🟢 {d.driver_name} iniciou a Especial.",
                                 "message_en": f"🟢 {d.driver_name} started the Stage."
                             }
                         )
                     )
            if manual_events:
                logger.info(f"🚨 Agent 03 inferred {len(manual_events)} new events!")
                for ev in manual_events:
                    logger.info(f"   💬 [{ev.severity}] {ev.message}")
                await set_cached_data(redis_timeline_key, [e.model_dump(mode='json') for e in manual_events], expiration_seconds=3600)
            
        # 2. Push new standings to Redis
        await set_cached_data(redis_times_key, tick_standings.model_dump(mode='json'), expiration_seconds=3600)
        logger.info(f"📤 Sent tick {i+1} standings to Redis.")
        
        # 3. Wait for Android App to poll
        if i < len(ticks) - 1:
            logger.info("⏳ Waiting 15 seconds for next tick...")
            await asyncio.sleep(15)
            
    logger.info("\n🏁 Simulation Complete.")

if __name__ == "__main__":
    from models.timeline import TimelineEvent, TimelineEventSource, TimelineEventSeverity
    import uuid
    asyncio.run(run_simulator())
