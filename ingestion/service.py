import asyncio
import logging
from datetime import datetime, date

logger = logging.getLogger(__name__)

from core.redis_service import set_cached_data
from core.database_service import get_all_events_from_db, get_last_archived_year, upsert_events
from ingestion.strategy import registry

# Ensure strategies are registered by importing clients
import ingestion.wrc_client
import ingestion.openf1_client

async def find_live_stages():
    """
    Scans the calendar from the DB to find events that are currently active.
    Then, fetches their stages using the appropriate Strategy to find which are 'Running'.
    """
    try:
        all_events = await get_all_events_from_db()
        today = date.today()

        live_stages = []
        for event in all_events:
            if event.start_date <= today <= event.finish_date:
                try:
                    strategy = registry.get_strategy(event.category)
                    stages = await strategy.fetch_event_stages(event.id)
                    live_stages.extend([(event.id, s.id, event.category, event.name, s.name) for s in stages if s.is_live])
                except ValueError as e:
                    logger.warning(f"Strategy error for event {event.id}: {e}")
                except Exception as e:
                    logger.error(f"Error fetching stages for live event {event.id}: {e}")

        return live_stages
    except Exception as e:
        logger.error(f"Error finding live stages: {e}")
        return []

async def run_live_timing_ingestion():
    """Ingests live timing data for all active events across all sports."""
    live_stages = await find_live_stages()

    if not live_stages:
        return

    for event_id, stage_id, category, event_name, stage_name in live_stages:
        try:
            strategy = registry.get_strategy(category)
            stage_standings = await strategy.fetch_live_timing(event_id, stage_id)
            if stage_standings:
                from core.redis_service import get_cached_data, set_cached_data
                redis_key = f"live:times:{category.lower()}:{stage_id}"
                
                # --- NOTIFICATION ENGINE ---
                if stage_standings.is_live:
                    notif_key = f"notification:sent:{category.lower()}:{stage_id}"
                    if not await get_cached_data(notif_key):
                        from core.notification_service import send_live_stage_notification
                        success_en = send_live_stage_notification(category, stage_id, stage_name, event_name, "en")
                        success_pt = send_live_stage_notification(category, stage_id, stage_name, event_name, "pt")
                        if success_en or success_pt:
                            await set_cached_data(notif_key, {"sent": True}, expiration_seconds=86400)

                # --- AGENT 03 WRC INFERENCE ---
                if category.lower() == "wrc":
                    from ingestion.agent_analyst import WRCAnalystAgent
                    from models.stage_times import StageStandings as SSModel
                    
                    old_data = await get_cached_data(redis_key)
                    if old_data:
                        try:
                            old_standings = SSModel(**old_data)
                            new_events = WRCAnalystAgent.analyze_wrc_timings(old_standings, stage_standings)
                            
                            if new_events:
                                timeline_key = f"timeline:wrc:{stage_id}"
                                existing_events_raw = await get_cached_data(timeline_key) or []
                                existing_events_raw.extend([e.model_dump(mode='json') for e in new_events])
                                await set_cached_data(timeline_key, existing_events_raw, expiration_seconds=86400) # Keep for 24h
                                
                                from core.database_service import save_timeline_events_to_db
                                from models.timeline import TimelineEvent
                                await save_timeline_events_to_db(str(stage_id), [TimelineEvent(**e) for e in existing_events_raw])
                                
                                # Send notifications for new timeline events
                                from core.notification_service import send_comment_notification
                                for e in new_events:
                                    for lang in ["en", "pt"]:
                                        lang_key = f"message_{lang}"
                                        msg_text = e.metadata.get(lang_key, e.message) if e.metadata else e.message
                                        preview = msg_text[:50] + ("..." if len(msg_text) > 50 else "")
                                        logger.info(f"Triggering {category.upper()} timeline push notification ({lang}) for stage {stage_id}: {preview}")
                                        send_comment_notification(category, stage_id, preview, language=lang)
                        except Exception as e:
                            logger.error(f"Error in Agent 03 WRC inference for Stage {stage_id}: {e}")
                
                # --- F1 TIMELINE NOTIFICATIONS ---
                if category.lower() == "f1":
                    from ingestion.openf1_client import fetch_f1_race_control_messages
                    from core.notification_service import send_comment_notification
                    
                    timeline_key = f"timeline:f1:{stage_id}"
                    try:
                        current_events = await fetch_f1_race_control_messages(stage_id)
                        if current_events:
                            cached_events_raw = await get_cached_data(timeline_key) or []
                            cached_ids = {str(e['id']) for e in cached_events_raw}
                            
                            new_events = [e for e in current_events if str(e.id) not in cached_ids]
                            
                            if new_events:
                                for e in new_events:
                                    for lang in ["en", "pt"]:
                                        lang_key = f"message_{lang}"
                                        msg_text = e.metadata.get(lang_key, e.message) if e.metadata else e.message
                                        preview = msg_text[:50] + ("..." if len(msg_text) > 50 else "")
                                        logger.info(f"Triggering {category.upper()} timeline push notification ({lang}) for session {stage_id}: {preview}")
                                        send_comment_notification(category, stage_id, preview, language=lang)
                                
                                await set_cached_data(timeline_key, [e.model_dump(mode='json') for e in current_events], expiration_seconds=86400)
                                
                                from core.database_service import save_timeline_events_to_db
                                await save_timeline_events_to_db(str(stage_id), current_events)
                    except Exception as e:
                        logger.error(f"Error processing F1 timeline notifications for Stage {stage_id}: {e}")
                        
                await set_cached_data(redis_key, stage_standings.model_dump(mode='json'), expiration_seconds=60)
        except Exception as e:
            logger.error(f"Error during {category} live ingestion for Stage {stage_id}: {e}")

async def run_overall_standings_ingestion():
    """Ingests overall standings once for running or recently completed events."""
    try:
        all_events = await get_all_events_from_db()
        today = date.today()

        for event in all_events:
            if event.start_date <= today <= event.finish_date or (event.finish_date < today and (today - event.finish_date).days < 3):
                try:
                    strategy = registry.get_strategy(event.category)
                    overall = await strategy.fetch_overall_standings(event.id)
                    if overall:
                        redis_key = f"overall:{event.category.lower()}:{event.id}"
                        await set_cached_data(redis_key, overall.model_dump(mode='json'), expiration_seconds=300)
                        from core.database_service import save_overall_standings_to_db
                        await save_overall_standings_to_db(event.id, overall)
                except Exception as e:
                    logger.error(f"Error fetching {event.category} overall standings for event {event.id}: {e}")
    except Exception as e:
        logger.error(f"Error finding events for overall standings ingestion: {e}")

async def run_championship_standings_ingestion():
    """Fetches and caches the championship standings for the current year for all sports."""
    logger.info("Running championship standings cache update for all sports...")
    current_year = datetime.now().year
    
    for category in registry.get_all_categories():
        try:
            strategy = registry.get_strategy(category)
            
            drivers = await strategy.fetch_driver_championship(current_year)
            if drivers:
                await set_cached_data(f"championship:drivers:{category.lower()}:{current_year}", drivers.model_dump(mode='json'), expiration_seconds=7200)

            teams = await strategy.fetch_team_championship(current_year)
            if teams:
                await set_cached_data(f"championship:teams:{category.lower()}:{current_year}", teams.model_dump(mode='json'), expiration_seconds=7200)
        except Exception as e:
            logger.error(f"Error updating championship standings cache for {category}: {e}")

async def run_historic_archive():
    """Archives past years for all registered sports."""
    logger.info("Running historic database archive for all sports...")
    try:
        last_archived_year = await get_last_archived_year()
        current_year = datetime.now().year
        years_to_archive = list(range(last_archived_year + 1, current_year))
        
        if not years_to_archive:
            return
            
        all_events = []
        for category in registry.get_all_categories():
            try:
                strategy = registry.get_strategy(category)
                events = await strategy.fetch_calendar_events(years_to_archive)
                all_events.extend(events or [])
            except Exception as e:
                logger.error(f"Error archiving past years for {category}: {e}")
                
        await upsert_events(all_events)
    except Exception as e:
        logger.error(f"Error in historic archive orchestration: {e}")

async def run_current_year_update():
    """Updates the current year's events for all registered sports."""
    logger.info("Running update for current year events for all sports...")
    try:
        current_year = datetime.now().year
        all_events = []
        
        for category in registry.get_all_categories():
            try:
                strategy = registry.get_strategy(category)
                events = await strategy.fetch_calendar_events([current_year])
                all_events.extend(events or [])
            except Exception as e:
                logger.error(f"Error updating current year events for {category}: {e}")
                
        await upsert_events(all_events)
    except Exception as e:
        logger.error(f"Error in current year update orchestration: {e}")

async def populate_historic_timeline(stage_id: int) -> list:
    """Populates historical timeline for a WRC stage combining basic system inference and Twitter scraping."""
    from core.database_service import get_stage_by_id_from_db, save_timeline_events_to_db, get_stage_times_from_db
    from ingestion.twitter_client import fetch_tweets_for_session
    from models.timeline import TimelineEvent, TimelineEventSource, TimelineEventSeverity
    import uuid
    from datetime import timezone, timedelta
    
    stage = await get_stage_by_id_from_db(stage_id)
    if not stage or not stage.start_time:
        return []
        
    start_time = stage.start_time
    if start_time.tzinfo is None:
        start_time = start_time.replace(tzinfo=timezone.utc)
    end_time = start_time + timedelta(hours=3) # Approx stage duration
    
    events = []
    # 1. Base events
    events.append(TimelineEvent(
        id=str(uuid.uuid4()),
        timestamp=start_time,
        source=TimelineEventSource.WRC_SYSTEM_INFERENCE,
        severity=TimelineEventSeverity.INFO,
        message=f"🟢 A Especial {stage.name} começou.",
        metadata={"message_pt": f"🟢 A Especial {stage.name} começou.", "message_en": f"🟢 Stage {stage.name} started."}
    ))
    
    events.append(TimelineEvent(
        id=str(uuid.uuid4()),
        timestamp=end_time,
        source=TimelineEventSource.WRC_SYSTEM_INFERENCE,
        severity=TimelineEventSeverity.INFO,
        message=f"🏁 A Especial {stage.name} foi concluída.",
        metadata={"message_pt": f"🏁 A Especial {stage.name} foi concluída.", "message_en": f"🏁 Stage {stage.name} was completed."}
    ))
    
    # 2. Driver results summary
    standings = await get_stage_times_from_db(stage_id, stage.event_id, "WRC")
    if standings and standings.standings:
        for i, st in enumerate(standings.standings[:15]): # top 15
            if st.status == "Finished":
                events.append(TimelineEvent(
                    id=str(uuid.uuid4()),
                    timestamp=start_time + timedelta(minutes=15 + i*2),
                    source=TimelineEventSource.WRC_SYSTEM_INFERENCE,
                    severity=TimelineEventSeverity.INFO,
                    message=f"🏁 {st.driver_name} terminou com o tempo de {st.time}.",
                    metadata={
                        "message_pt": f"🏁 {st.driver_name} terminou com o tempo de {st.time}.",
                        "message_en": f"🏁 {st.driver_name} finished with a time of {st.time}."
                    }
                ))

    # 3. Twitter Scraping
    try:
        tweets = await fetch_tweets_for_session(start_time, end_time, "from:OfficialWRC", TimelineEventSource.WRC_SOCIAL_MEDIA, "@OfficialWRC")
        if tweets:
            events.extend(tweets)
    except Exception as e:
        logger.error(f"Error fetching historical tweets for stage {stage_id}: {e}")
        
    events.sort(key=lambda x: x.timestamp)
    
    await save_timeline_events_to_db(str(stage_id), events)
    return events
