# Grid Pace BFF API

## 1. Overview

**Grid Pace BFF (Backend For Frontend)** is a Python API built with FastAPI that serves as an optimized bridge between the **Grid Pace** Android application and official motorsport data sources (WRC and OpenF1).

Its mission is to fetch, clean, format, and serve data perfectly tailored for the application's UI needs. It is built on a modern, scalable, event-driven architecture to provide high performance and resilience.

### Architecture & Tech Stack

- **Language:** Python 3.x
- **Framework:** FastAPI
- **Server:** Uvicorn (for local development)
- **Data Extraction:**
  - [OpenWRC](https://github.com/andreiamrsilva/OpenWRC.git) for WRC data.
  - [OpenF1 API](https://openf1.org/) for Formula 1 data.
- **Database (Historic Data):** SQLite (local) / PostgreSQL (production) via SQLAlchemy.
- **Cache & Live Data:** Redis.
- **Data Validation:** Pydantic.

## 2. Architecture Deep Dive

The system relies on a Serverless-first architecture:

1.  **FastAPI Server (`main.py`):**
    *   The public-facing API that the Android app communicates with.
    *   **It does not perform heavy computations or external API calls on demand.**
    *   Its primary role is to read pre-processed data from the Redis cache or the historic database, ensuring fast responses.

2.  **Cron Endpoints (`api/routers/cron.py`):**
    *   The system exposes HTTP endpoints under `/cron` which trigger data ingestion.
    *   These endpoints are designed to be invoked periodically by a Serverless Cron scheduler (like Vercel Cron).
    *   They fetch data for live events, calculate standings, update the Redis cache, and populate the historic database.

This separation allows the app to be deployed in "scale-to-zero" serverless environments.

## 3. Installation & Setup

### Prerequisites

-   Python 3.10+
-   Git
-   Docker (for running Redis locally)

### Setup Steps

1.  **Clone the Repository:**
    ```bash
    git clone https://github.com/andreiamrsilva/grid-pace-bff.git
    cd grid-pace-bff
    ```

2.  **Initialize Submodules:**
    ```bash
    git submodule update --init --recursive
    ```

3.  **Start Redis using Docker:**
    Make sure Docker Desktop is running, then execute:
    ```bash
    docker run -d --name grid-pace-redis -p 6379:6379 redis
    ```

4.  **Create Virtual Environment & Install Dependencies:**
    ```bash
    python -m venv .venv
    source .venv/bin/activate  # On Windows: .venv\Scripts\activate
    pip install -r requirements.txt
    ```

5.  **Run the Application:**
    Start the API Server:
    ```bash
    uvicorn main:app --reload
    ```

    The API will be available at `http://127.0.0.1:8000`.

6.  **Trigger Data Ingestion (Local Development):**
    Because the background worker was migrated to Cron endpoints for serverless compatibility, you must manually trigger data ingestion to populate the database and cache locally.
    You can do this by opening the Swagger UI (`http://127.0.0.1:8000/docs`) and executing the POST endpoints under the **Cron Jobs** section, or by using cURL:
    ```bash
    # Populate historic data
    curl -X POST http://127.0.0.1:8000/cron/archive-historic
    
    # Update current year events
    curl -X POST http://127.0.0.1:8000/cron/update-current-year
    
    # Ingest live timings
    curl -X POST http://127.0.0.1:8000/cron/ingest-live-timing
    ```

## 4. API Documentation

Interactive documentation is available after starting the server:

-   **Swagger UI:** `http://127.0.0.1:8000/docs`
-   **ReDoc:** `http://127.0.0.1:8000/redoc`

### Available Routes

---

### 4.1. Calendar (`GET /calendar`)

Retrieves the motorsport events calendar for WRC and F1. Supports filtering by `categories` (WRC, F1) and `year`.

---

### 4.2. Event Briefing (`GET /events/{category}/{event_id}/briefing`)

Returns a comprehensive pre-event briefing for an upcoming F1 or WRC event. Provides weather forecasts for event days, circuit/rally metadata (city, country, surface type, total distance, lap count for F1), tactical briefing, start time and location of the 1st stage/session, last winner, event/lap record, and track layout map URL.

---

### 4.3. Event Stages / Sessions (`GET /events/{category}/{event_id}/stages`)

Returns the list of stages (WRC) or sessions (F1) for a specific event. Data is served using a multi-layer cache strategy (Redis -> SQLite DB -> Upstream APIs).

---

### 4.4. Stage Times (`GET /events/{category}/{event_id}/stages/{stage_id}/times`)

Returns live or final timings for a specific stage or session. Supports Smart Polling via `last_sync_time` (returns HTTP 304 if no new data is available).

---

### 4.5. Overall Event Standings (`GET /events/{category}/{event_id}/overall`)

Returns current or final overall standings for a specific event (cumulative driver positions, time gaps, and points).

---

### 4.6. Driver Championship Standings (`GET /championship/drivers/{year}`)

Returns the overall driver championship standings for a given year and categories (`WRC`, `F1`).

---

### 4.7. Team Championship Standings (`GET /championship/teams/{year}`)

Returns the overall team/constructor championship standings for a given year and categories (`WRC`, `F1`).

---

### 4.8. Motorsport News (`GET /news`)

Retrieves the latest news articles for specified categories (`WRC`, `F1`) and language (`pt`, `en`). Cached for 15 minutes.

---

### 4.9. Live Timeline & Race Control (`GET /api/v1/timeline/{category}/{session_id}`)

Retrieves a chronologically ordered feed of live events, incidents, race control messages, driver quotes, and social media updates for a session. Supports Smart Polling (`last_event_time`) and multilanguage commentary (`language`).

---

### 4.10. User Profile & Settings (`GET /api/v1/users/me`, `PATCH /api/v1/users/me/settings`)

- `GET /api/v1/users/me`: Gets or creates the current user profile, subscription status, and notification preferences.
- `PATCH /api/v1/users/me/settings`: Updates notification preferences and followed categories.

---

### 4.11. Cron Jobs (`GET /cron/*`)

Protected endpoints triggered by serverless schedulers to ingest and cache motorsport data:
- `GET /cron/ingest-live-timing`: Ingests live timings for active sessions.
- `GET /cron/ingest-overall-standings`: Ingests event overall standings.
- `GET /cron/ingest-championship`: Ingests driver and team championship standings.
- `GET /cron/update-current-year`: Updates calendar and stages for current year events.
- `GET /cron/archive-historic`: Archives historic data into the permanent database.
- `GET /cron/validate-timeline-tweets`: Backfills missing social media commentary for recent stages.

