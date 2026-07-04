# OpenWRC

A local data sink and query toolkit for WRC (World Rally Championship) event data.

OpenWRC fetches data from the official WRC API and stores it in a local SQLite database, then exposes clean Python interfaces for exploring it — either programmatically via a session object or interactively via a Streamlit dashboard.

---

## Architecture

The project is split into two layers:

### `src/openwrc/` — Core library

The core package handles everything related to data: fetching, storing, and querying.

**Data sink** — `WrcApiClient` pulls event data from the WRC API. `DataStoreService` maps the API responses into local DB models and persists them via SQLAlchemy. The local database (`wrc.db`) is a SQLite file that acts as a cache of WRC event data.

**Session interface** — `WrcSession` is the main entry point for working with stored data. It resolves an event and rally once at creation time, then exposes query methods that use those resolved IDs automatically.

```python
session = await WrcSession.create(name="monte carlo", year=2026)

standings = await session.flat_standings()
split_times = await session.flat_split_times(stage_number=3)
entries = await session.entries()
stages = await session.stages()
```

Before creating a session, two class methods let you discover what's available in the local DB:

```python
years = await WrcSession.list_available_years()
events = await WrcSession.list_events_for_year(2026)
```

**Denormalized views** — `v_standings` and `v_split_times` are SQLite views that join standings/split times with driver, manufacturer, entrant, and class identity. Queried via `flat_standings()` and `flat_split_times()`, which return typed Pydantic models (`FlatStandingRow`, `FlatSplitTimeRow`).

### `src/visualizations/` — Dashboard

An interactive Streamlit dashboard for exploring rally data visually.

---

## Setup

**Install dependencies:**
```bash
uv sync
```

**Populate the local database** by running the ETL for the events you want. See `src/openwrc/storage/data_store_service.py` or `main.py`.

---

## Running the dashboard

```bash
streamlit run src/visualizations/dashboard.py
```

Opens at `http://localhost:8501`. Select a year and event from the sidebar, then explore:

- **Standings Progression** — gap to first, overall position, or total time across stages. Filter by class, driver, and stage range.
- **Stage Split Times** — cumulative delta to split leader at each intermediate split point within a stage. Filter by class and driver.

**Enable query timing logs** (prints SQL execution times to the terminal):
```bash
WRC_DEBUG_SQL=1 streamlit run src/visualizations/dashboard.py
```

---
