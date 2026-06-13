import sqlite3
from typing import List
from models.calendar import CalendarEvent
from datetime import date
import logging
import os

logger = logging.getLogger(__name__)

DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "historic_events.db"))

def init_db():
    """Initializes the SQLite database and creates the necessary tables."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS historic_events (
            id INTEGER,
            category TEXT,
            name TEXT,
            country TEXT,
            country_image_url TEXT,
            start_date DATE,
            finish_date DATE,
            current_leader TEXT,
            current_leader_logo_path TEXT,
            PRIMARY KEY (id, category)
        )
    ''')
    conn.commit()
    conn.close()
    logger.info("Database initialized.")

def insert_events(events: List[CalendarEvent]):
    """Inserts or replaces events in the database."""
    if not events:
        return
        
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    for event in events:
        cursor.execute('''
            INSERT OR REPLACE INTO historic_events 
            (id, category, name, country, country_image_url, start_date, finish_date, current_leader, current_leader_logo_path)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            event.id,
            event.category,
            event.name,
            event.country,
            event.country_image_url,
            event.start_date.isoformat(),
            event.finish_date.isoformat(),
            event.current_leader,
            event.current_leader_logo_path
        ))
        
    conn.commit()
    conn.close()
    logger.info(f"Inserted {len(events)} events into the database.")

def get_historic_events() -> List[CalendarEvent]:
    """Retrieves all historic events from the database."""
    events = []
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM historic_events')
        rows = cursor.fetchall()
        
        for row in rows:
            events.append(CalendarEvent(
                id=row[0],
                category=row[1],
                name=row[2],
                country=row[3],
                country_image_url=row[4],
                start_date=date.fromisoformat(row[5]),
                finish_date=date.fromisoformat(row[6]),
                current_leader=row[7],
                current_leader_logo_path=row[8]
            ))
            
        conn.close()
    except Exception as e:
        logger.error(f"Error reading from database: {e}")
        
    return events

def get_stored_years() -> List[int]:
    """Returns a list of distinct years currently stored in the database."""
    years = set()
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('SELECT DISTINCT strftime("%Y", start_date) FROM historic_events')
        rows = cursor.fetchall()
        for row in rows:
            if row[0]:
                years.add(int(row[0]))
        conn.close()
    except Exception as e:
        logger.error(f"Error reading years from database: {e}")
    return list(years)
