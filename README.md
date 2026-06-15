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

The system is composed of two main services designed for performance and scalability:

1.  **FastAPI Server (`main.py`):**
    *   The public-facing API that the Android app communicates with.
    *   **It does not perform heavy computations or external API calls on demand.**
    *   Its primary role is to read pre-processed data from the Redis cache or the historic database, ensuring responses are always fast (typically <50ms).

2.  **Ingestion Worker (`ingestion_worker.py`):**
    *   A background process that runs continuously.
    *   It is the **only** part of the system that communicates with the slow, external WRC and OpenF1 APIs.
    *   It periodically fetches data for live events, calculates standings, and updates the Redis cache.
    *   It is also responsible for populating the historic database on startup.

This separation ensures that the user-facing API remains fast and responsive, regardless of the performance or availability of the external data sources.

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
    You need to run **two separate processes** in two different terminals.

    *   **Terminal 1: Start the API Server:**
        ```bash
        uvicorn main:app --reload
        ```
    *   **Terminal 2: Start the Ingestion Worker:**
        ```bash
        python ingestion_worker.py
        ```

    The API will be available at `http://127.0.0.1:8000`. On the first run, the worker will take a few minutes to populate the historic database.

## 4. API Documentation

Interactive documentation is available after starting the server:

-   **Swagger UI:** `http://127.0.0.1:8000/docs`
-   **ReDoc:** `http://127.0.0.1:8000/redoc`

### Available Routes

---

### 4.1. Calendar (`GET /calendar`)

Retrieves the motorsport events calendar. It combines long-term historic data from a database with fresh, frequently updated data for the current and next year from a cache.

---

### 4.2. Event Stages (`GET /events/{category}/{event_id}/stages`)

Returns the list of stages (WRC) or sessions (F1) for a specific event. This data is served from a Redis cache that is pre-warmed and kept up-to-date by the background worker for active events, ensuring instant responses.

---

### 4.3. Stage Times (`GET /events/{category}/{event_id}/stages/{stage_id}/times`)

Returns the live or final timings for a specific stage/session. This endpoint reads directly from the Redis cache, which is populated every 15 seconds by the `ingestion_worker` for any live stage, providing a near-real-time experience.
