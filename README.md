# Grid Pace BFF API

## 1. Overview

**Grid Pace BFF (Backend For Frontend)** is a Python API built with FastAPI that serves as an optimized bridge between the **Grid Pace** Android application and the official motorsport data sources (currently focused on the Red Bull/WRC rally API).

Its mission is to fetch, clean, format, and serve data perfectly tailored for the application's UI needs, ensuring high performance, resilience, and a smooth user experience.

### Architecture & Tech Stack

- **Language:** Python 3.x
- **Framework:** FastAPI
- **Server:** Uvicorn
- **Data Extraction:** Integration with [OpenWRC](https://github.com/andreiamrsilva/OpenWRC.git) (personal fork).
- **Data Validation:** Pydantic

## 2. Installation & Setup

### Prerequisites

- Python 3.10+
- Git

### Setup Steps

1.  **Clone the Repository:**
    ```bash
    git clone https://github.com/andreiamrsilva/grid-pace-bff.git
    cd grid-pace-bff
    ```

2.  **Initialize the OpenWRC Submodule:**
    The project depends on `OpenWRC` as a Git submodule. To initialize it:
    ```bash
    git submodule update --init --recursive
    ```

3.  **Create a Virtual Environment and Install Dependencies:**
    ```bash
    python -m venv .venv
    source .venv/bin/activate  # On Windows: .venv\Scripts\activate
    pip install -r requirements.txt
    ```

4.  **Run the Development Server:**
    ```bash
    uvicorn main:app --reload
    ```
    The API will be available at `http://127.0.0.1:8000`.

## 3. API Documentation

The API automatically generates interactive documentation. After starting the server, you can access:

- **Swagger UI:** `http://127.0.0.1:8000/docs`
- **ReDoc:** `http://127.0.0.1:8000/redoc`

### Available Routes

---

### 3.1. Calendar

Retrieves the rally events calendar.

#### `GET /calendar`

Returns a list of calendar events. The data is served from an in-memory cache that is automatically updated in the background every 5 minutes.

**Query Parameters:**

-   `year` (Optional, `int`): Filters the events for a specific year. If not provided, it returns events from all available years.

**Example Request:**

```
GET http://127.0.0.1:8000/calendar?year=2024
```

**Example Response (`200 OK`):**

```json
[
  {
    "id": 635,
    "name": "FORUM8 Rally Japan",
    "country": "Japan",
    "country_image_url": "https://flagcdn.com/w320/jp.png",
    "start_date": "2024-11-21",
    "finish_date": "2024-11-24",
    "current_leader": "Thierry Neuville",
    "current_leader_team_logo": "hyundai.png"
  },
  {
    "id": 634,
    "name": "Central European Rally",
    "country": "Central Europe",
    "country_image_url": "https://flagcdn.com/w320/eu.png",
    "start_date": "2024-10-31",
    "finish_date": "2024-11-03",
    "current_leader": null,
    "current_leader_team_logo": null
  }
]
```

---

### 3.2. Events

Provides details about a specific event.

#### `GET /events/{event_id}/stages`

Returns a list of all stages for a given event.

**Path Parameters:**

-   `event_id` (Required, `int`): The unique identifier of the event.

**Example Request:**

```
GET http://127.0.0.1:8000/events/635/stages
```

**Example Response (`200 OK`):**

```json
[
  {
    "id": 10401,
    "name": "Isegami's Tunnel",
    "number": 1,
    "distance": 23.67,
    "start_time": "2024-11-21T17:00:00Z",
    "status": "Completed",
    "is_live": false,
    "winner_name": "Sébastien Ogier",
    "winner_team_logo": "toyota.png",
    "winner_time": "12:45.3"
  },
  {
    "id": 10402,
    "name": "Okazaki City",
    "number": 2,
    "distance": 12.5,
    "start_time": "2024-11-22T10:04:00Z",
    "status": "Running",
    "is_live": true,
    "winner_name": null,
    "winner_team_logo": null,
    "winner_time": null
  }
]
```