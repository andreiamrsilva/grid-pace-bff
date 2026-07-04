# Result Models Design Reasoning

## Overview

This document explains the design decisions for the result models in `result.py`, which persist timing and standings data from the WRC API.

## Core Requirements

The models need to efficiently answer these analytical queries:

1. **Driver's rally journey**: All stage times for one driver across a rally
2. **Time loss analysis**: Which stages did drivers lose time to the leader?
3. **Position change analysis**: Where do significant position shifts happen?

## Design Decisions

### 1. StageTime - Individual Stage Performance

**Purpose**: Track each driver's performance on individual stages.

**Key Decisions**:

- **Composite PK `(stage_id, entry_id)`**: Natural key enforces one record per driver per stage
- **Denormalized `rally_id`**: Critical for query efficiency

**Reasoning**:

Without denormalization, the query "give me all stage times for driver X in rally Y" requires:
```
StageTime → Entry → Rally
```
That's **2 joins** to filter by rally.

With `rally_id` denormalized:
```sql
SELECT * FROM stage_times
WHERE rally_id = X AND entry_id = Y
ORDER BY stage_id
```
**Zero joins** ✅

**Note**: `event_id` is NOT denormalized - it can be derived via `entry_id → rally_id → event_id` or `stage_id → event_id`. This avoids triple redundancy while maintaining query performance.

**Trade-off**: 8 bytes of storage per row vs massive query performance improvement.

### 2. RallyStanding - Overall Standings Evolution

**Purpose**: Capture overall rally standings after each stage, enabling position change analysis.

**Key Decisions**:

- **Composite PK `(rally_id, stage_id, entry_id)`**: The `stage_id` represents "standing after completing this stage"
- **Stores cumulative data**: `stage_time_ms`, `penalty_time_ms`, `total_time_ms`
- **No `event_id` denormalization**: Already accessible via `rally_id → event_id`, `stage_id → event_id`, and `entry_id → rally_id → event_id` (triple redundancy avoided)

**Reasoning**:

This is a **state snapshot table** - it captures the rally standings at specific points in time (after each stage). This pattern enables:

- "Show me position changes between SS5 and SS6": Query standings for both stages, compare positions
- "When did driver X drop from 2nd to 4th?": Find where `position` changes
- "Time gap evolution": Track `diff_first_ms` across stages

**Important Discovery**: The WRC API's "rally results" endpoint returns data identical to the last stage's results. Therefore:
- Rally results = Stage results for the final stage
- No separate "final results" table needed
- Query for final standings: `WHERE rally_id = X AND stage_id = (SELECT MAX(stage_id) ...)`

**Alternative considered**: Store only stage-by-stage times and compute standings on-the-fly.
**Rejected because**: Recomputing cumulative times for every query is expensive, and standings are immutable once a stage is complete.

### 3. ShakedownTime - Pre-Rally Practice

**Purpose**: Track shakedown runs (pre-rally practice stages).

**Key Decisions**:

- **Single PK `shakedown_time_id`**: API provides this ID
- **Keep `event_id`**: API endpoint uses event_id (not rally_id) and explicitly returns it
- **No `rally_id`**: Though entries are rally-specific, shakedown is conceptually event-scoped

**Reasoning**:

Shakedown times are queried differently than competitive stages:
- API uses `get_event_shakedown_results(event_id)` (no rally_id parameter)
- Usually viewed per event, not per rally
- Multiple runs per driver (run_number = 1, 2, 3...)
- Not part of rally standings

**Discovery from data**: Even though entries are rally-specific (e.g., Event 590 had separate "National" and "Regional" rally entries), shakedown is accessed via event_id only. The API design suggests shakedown is intended to be event-level, even though specific rally entries participate.

Simple model matches simple query patterns and API structure.

### 4. SplitTime - Intermediate Timing Points

**Purpose**: Store intermediate split times within stages.

**Key Decisions**:

- **Single PK `split_point_time_id`**: API-provided identifier
- **No denormalized IDs**: Can access via `entry_id → rally_id → event_id` or `stage_id → event_id`

**Reasoning**:

Split times are always queried in the context of a specific stage:
- "Show me split times for SS5"
- "Compare driver X and Y at split point 3 on SS8"

The query pattern is:
```sql
SELECT * FROM split_times
WHERE stage_id = X AND entry_id IN (Y, Z)
ORDER BY split_point_id
```

We always filter by `stage_id` first, which provides enough context. Adding `event_id` or `rally_id` would be redundant since:
- `stage_id → event_id` (stages belong to events)
- `entry_id → rally_id → event_id` (entries belong to rallies)

Keep it simple - no denormalization needed.

## Denormalization Strategy Summary

| Model | Denormalized Fields | Reasoning |
|-------|-------------------|-----------|
| `StageTime` | `rally_id` | Frequent "all times in rally" queries; event_id accessible via entry or stage |
| `RallyStanding` | None | rally_id in PK; triple redundancy avoided (rally_id, stage_id, entry_id all → event_id) |
| `ShakedownTime` | `event_id` | API uses event_id; shakedown conceptually event-scoped |
| `SplitTime` | None | Always queried by stage_id; no denormalization needed |

## Index Strategy

**Principle**: Index on frequent filter combinations, ordered by selectivity (most selective first).

- `StageTime`:
  - `(rally_id, entry_id)` - "Driver's rally journey" query
  - `(stage_id)` - "All times for this stage" query

- `RallyStanding`:
  - `(rally_id, entry_id)` - "Driver's standing progression" (rally_id in PK provides this)
  - `(rally_id, stage_id)` - "All standings after this stage" (both in PK provides this)

- `ShakedownTime`:
  - `(event_id, entry_id)` - "Driver's shakedown runs"

- `SplitTime`:
  - `(stage_id, entry_id)` - "Driver's splits on this stage"

**Note**: RallyStanding indexes are automatically efficient due to composite PK structure.

## Enums vs Strings

**Decision**: Use Python enums (`StageStatus`, `DataSource`) instead of raw strings.

**Reasoning**:
- Type safety in application code
- Enforces valid values at DB level
- Self-documenting (IDE autocomplete shows valid options)
- Easier to extend (add new enum value in one place)

**Trade-off**: Schema migrations needed when adding new enum values (acceptable for relatively static data).

## Query Pattern Validation

### Query 1: "Give me one driver's rally journey"

```python
stage_times = await session.execute(
    select(StageTime)
    .where(StageTime.rally_id == 123, StageTime.entry_id == 456)
    .order_by(StageTime.stage_id)
)
```

**Joins needed**: 0 ✅
**Index used**: `ix_stage_time_rally_entry` ✅

### Query 2: "Which stages do drivers lose time to leader?"

```python
standings = await session.execute(
    select(RallyStanding)
    .where(RallyStanding.rally_id == 123, RallyStanding.entry_id == 456)
    .order_by(RallyStanding.stage_id)
)
# In Python: find stages where diff_first_ms[i] > diff_first_ms[i-1]
```

**Joins needed**: 0 ✅
**Index used**: `ix_rally_standing_rally_entry` ✅

### Query 3: "Which stages see significant position changes?"

```python
# Get standings for consecutive stages
prev_standings = await session.execute(
    select(RallyStanding)
    .where(RallyStanding.rally_id == 123, RallyStanding.stage_id == 5)
    .order_by(RallyStanding.position)
)
curr_standings = await session.execute(
    select(RallyStanding)
    .where(RallyStanding.rally_id == 123, RallyStanding.stage_id == 6)
    .order_by(RallyStanding.position)
)
# Compare positions in Python
```

**Joins needed**: 0 ✅
**Index used**: `ix_rally_standing_rally_stage` ✅

## API Mapping

| API Model | DB Model | Mapper Complexity |
|-----------|----------|-------------------|
| `ApiStageTimeEntry` | `StageTime` | Low - direct field mapping + denorm lookups |
| `ApiResultEntry` | `RallyStanding` | Medium - needs stage context from API call |
| `ApiShakedownTimeEntry` | `ShakedownTime` | Low - direct field mapping |
| `ApiSplitTimeEntry` | `SplitTime` | Low - direct field mapping |

**Note on `ApiResultEntry` → `RallyStanding`**:

The API model `ApiResultEntry` is used for both:
1. Rally results (overall standings) - via `get_rally_results(event_id, rally_id)`
2. Stage results (cumulative standings after each stage) - via `get_event_stage_results(event_id, stage_id, rally_id)`

**Critical discovery**: Rally results and final stage results are **identical**. The rally results endpoint returns the same data as querying the last stage's results. Therefore, we only need the `RallyStanding` table.

The API returns only `entry_id` and result fields - no `rally_id`, `stage_id`, or `event_id`. The mapper must denormalize these from API call context:

```python
def map_api_result_to_rally_standing(
    api_result: ApiResultEntry,
    rally_id: int,      # From API call context
    stage_id: int,      # From API call context
) -> RallyStanding:
    # event_id not needed - can be derived from rally_id
    ...
```

## Future Considerations

### Data Discoveries

Through API investigation (Event 590 - Lake Superior Performance Rally), we discovered:

1. **Events CAN have multiple rallies**: E.g., "National" (22 entries, 15 stages) vs "Regional" (50 entries, 14 stages)
2. **Entries are rally-specific**: Zero overlap between rally entry lists - completely different drivers
3. **Stages are event-level**: Shared across rallies (14 of 15 stages shared, Regional skipped one)
4. **Each rally has its own itinerary**: Different itinerary_ids referencing shared stages
5. **Rally results = Last stage results**: API's rally results endpoint returns identical data to final stage

These findings validate our schema design:
- `Entry` has only `rally_id` FK (not `event_id` - would be redundant)
- `Stage` has only `event_id` FK (stages are shared event-level resources)
- `Itinerary` has both `event_id` and `rally_id` FKs (each rally schedules shared stages)

### Missing Tables

1. **SplitPoint**: The API references `split_point_id` but we don't model the split point entity itself. Consider adding if we need split point metadata (location, distance, etc.).

### Read-Heavy Optimization

These models assume read:write ratio > 10:1 (typical for historical results):
- Results are written once per stage completion
- Results are queried many times for analysis

If live leaderboard updates become frequent, consider:
- Separate "live" vs "final" tables
- Materialized views for common aggregations
- Caching layer for hot queries

### Storage Growth

With minimal denormalization, storage grows linearly:
- `StageTime`: ~50 entries/stage × 20 stages × N rallies
- `RallyStanding`: ~50 entries/stage × 20 stages × N rallies

At 100 rallies/year × 10 years = 1M rows, still easily manageable in SQLite/PostgreSQL.

## Validation

✅ All analytical query patterns can be answered with 0-1 joins
✅ Composite PKs prevent duplicate data
✅ Indexes cover common filter patterns
✅ Enums provide type safety
✅ Nullable fields explicitly marked
✅ Denormalization justified by query patterns
