from models.stage_times import StageStandings
from models.timeline import TimelineEvent, TimelineEventSource, TimelineEventSeverity
from typing import List
from datetime import datetime, timezone
import uuid

class WRCAnalystAgent:
    """
    Agent 03: The Data Analyst
    Responsible for deducing real-time events from state changes in live timing.
    """
    
    @staticmethod
    def analyze_wrc_timings(old_standings: StageStandings, new_standings: StageStandings) -> List[TimelineEvent]:
        """
        Analyzes the difference between the old and new standings and generates
        TimelineEvents (inferred commentary) based on rules.
        """
        events: List[TimelineEvent] = []
        now = datetime.now(timezone.utc)
        
        old_drivers = {d.entry_id: d for d in old_standings.standings}
        
        for new_driver in new_standings.standings:
            entry_id = new_driver.entry_id
            name = new_driver.driver_name
            
            old_driver = old_drivers.get(entry_id)
            
            # Rule 1: Started the stage
            if not old_driver and new_driver.status == "OnTrack":
                events.append(TimelineEvent(
                    id=str(uuid.uuid4()),
                    timestamp=now,
                    source=TimelineEventSource.WRC_SYSTEM_INFERENCE,
                    severity=TimelineEventSeverity.INFO,
                    message=f"🟢 {name} iniciou a Especial.",
                    driver_name=name,
                    metadata={
                        "message_pt": f"🟢 {name} iniciou a Especial.",
                        "message_en": f"🟢 {name} started the Stage."
                    }
                ))
            
            # Follow-up rules if driver was already tracked
            if old_driver:
                # Rule 2: Retired / Stopped
                if old_driver.status == "OnTrack" and new_driver.status in ["Retired", "Stopped", "DidNotFinish"]:
                    events.append(TimelineEvent(
                        id=str(uuid.uuid4()),
                        timestamp=now,
                        source=TimelineEventSource.WRC_SYSTEM_INFERENCE,
                        severity=TimelineEventSeverity.CRITICAL,
                        message=f"❌ {name} abandonou a Especial.",
                        driver_name=name,
                        metadata={
                            "message_pt": f"❌ {name} abandonou a Especial.",
                            "message_en": f"❌ {name} retired from the Stage."
                        }
                    ))
                
                # Rule 4: Finished
                if old_driver.status == "OnTrack" and new_driver.status == "Finished":
                    time_str_pt = f" com o tempo de {new_driver.time}" if new_driver.time else ""
                    time_str_en = f" with a time of {new_driver.time}" if new_driver.time else ""
                    events.append(TimelineEvent(
                        id=str(uuid.uuid4()),
                        timestamp=now,
                        source=TimelineEventSource.WRC_SYSTEM_INFERENCE,
                        severity=TimelineEventSeverity.INFO,
                        message=f"🏁 {name} terminou a Especial{time_str_pt}.",
                        driver_name=name,
                        metadata={
                            "message_pt": f"🏁 {name} terminou a Especial{time_str_pt}.",
                            "message_en": f"🏁 {name} finished the Stage{time_str_en}."
                        }
                    ))
                
                # Rule 3: Significant position drop
                if old_driver.position and new_driver.position:
                    drop = new_driver.position - old_driver.position
                    if drop >= 3 and new_driver.status in ["OnTrack", "Finished"]:
                        events.append(TimelineEvent(
                            id=str(uuid.uuid4()),
                            timestamp=now,
                            source=TimelineEventSource.WRC_SYSTEM_INFERENCE,
                            severity=TimelineEventSeverity.WARNING,
                            message=f"⚠️ {name} perdeu tempo significativo, caindo para a {new_driver.position}ª posição.",
                            driver_name=name,
                            metadata={
                                "message_pt": f"⚠️ {name} perdeu tempo significativo, caindo para a {new_driver.position}ª posição.",
                                "message_en": f"⚠️ {name} lost significant time, dropping to position {new_driver.position}."
                            }
                        ))
                        
        return events
