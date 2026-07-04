---
name: api-to-db-model-design
description: Design database persistence models from external API models optimized for analytical queries. Use when creating DB schemas, analyzing query patterns, or mapping external APIs to internal storage.
---

# API to DB Model Design

Design database models that persist external API data while optimizing for analytical query patterns.

## Core Principles

### 1. Denormalization for Read Performance

**Default**: Start normalized, denormalize for proven query patterns.

**Common denormalizations**:
- Add parent foreign keys (e.g., `stage_id` + `event_id` to avoid 4-table joins)
- Duplicate hierarchical IDs (e.g., `Stage.rally_id` when querying "all stages in rally")
- Pre-compute aggregates (e.g., `total_time_ms = stage_time_ms + penalty_time_ms`)

**When to denormalize**:
- Query pattern appears 3+ times in requirements
- Join depth > 3 tables for common queries
- Read:write ratio > 10:1 (typical for results data)

### 2. Composite Keys for Fact Tables

Use composite primary keys for time-series and result data:

```python
# Good - natural composite key
class StageTime(Base):
    stage_id: Mapped[int] = mapped_column(ForeignKey(...), primary_key=True)
    entry_id: Mapped[int] = mapped_column(ForeignKey(...), primary_key=True)
```

**Why**: Enforces uniqueness, no synthetic ID overhead, clear semantics.

### 3. Capture State Transitions

For evolving data (standings, positions), capture state **after each change**:

```python
class RallyStanding(Base):
    rally_id: Mapped[int] = mapped_column(primary_key=True)
    stage_id: Mapped[int] = mapped_column(primary_key=True)  # "after this stage"
    entry_id: Mapped[int] = mapped_column(primary_key=True)
    position: Mapped[int | None]
    total_time_ms: Mapped[int]
```

Enables: "Show me position changes between stages", "When did driver X lose time?"

## Design Workflow

### Step 1: Analyze API Models

Extract:
1. **Entities** (nouns): `Entry`, `Stage`, `Event`
2. **Facts** (measurements): `stage_time_ms`, `position`, `diff_first_ms`
3. **Relationships**: `entry_id → Entry`, `stage_id → Stage`
4. **Temporal aspects**: Does data represent a point-in-time snapshot?

### Step 2: Identify Query Patterns

List specific analytical questions:
- "Give me one driver's full rally journey"
- "Which stage had the most position changes?"
- "Show time gaps to leader after each stage"

For each pattern:
- What tables are involved?
- How many joins are needed?
- Is this a hot path (frequent query)?

### Step 3: Design Schema

**For each API model**:

1. **Choose primary key strategy**:
   - Single entity? → Single PK (`person_id`, `event_id`)
   - Fact/measurement? → Composite PK (`stage_id, entry_id`)
   - Event log? → Synthetic PK + timestamp

2. **Map fields directly**:
   - Copy scalar fields (primitives, strings)
   - Convert nested objects to foreign keys
   - Store enums as enums (not strings)

3. **Add denormalized fields**:
   - For each foreign key, ask: "Will I query by the parent's parent?"
   - Example: `StageTime.stage_id` → add `event_id`, `rally_id` if querying "all stage times in rally"

4. **Add computed fields** (optional):
   - If API sends `stage_time_ms` and `penalty_time_ms`, optionally pre-compute `total_time_ms`
   - Only if computation is non-trivial or queried frequently

### Step 4: Validate Against Query Patterns

For each query pattern from Step 2, write pseudocode:

```python
# Pattern: "Driver's rally journey"
stage_times = select(StageTime).where(
    StageTime.rally_id == X,  # ✅ Direct filter (denormalized)
    StageTime.entry_id == Y
)
# Joins needed: 0 ✅
```

If joins > 2 for common query → **add denormalized field**.

### Step 5: Define Indexes

For each frequent filter/join:
```python
__table_args__ = (
    Index('ix_stage_time_rally_entry', 'rally_id', 'entry_id'),
    Index('ix_stage_time_stage', 'stage_id'),
)
```

## Denormalization Decision Matrix

| Scenario | Action | Example |
|----------|--------|---------|
| Join depth ≤ 2 | Keep normalized | `Entry → Person` |
| Join depth 3-4, infrequent query | Keep normalized | `Stage → Section → Leg → Itinerary` (for schema browsing) |
| Join depth 3-4, frequent query | **Denormalize** | `StageTime.rally_id` (for "all times in rally") |
| Pre-computed sum/aggregate | **Denormalize** | `total_time_ms = stage + penalty` |
| Data changes frequently | Keep normalized | Live leaderboard (use views) |
| Data immutable after insert | **Denormalize freely** | Historical results |

## Common Patterns

### Pattern 1: Fact Table

**Use for**: Measurements, time-series, results

```python
class StageTime(Base):
    __tablename__ = "stage_times"

    # Composite PK
    stage_id: Mapped[int] = mapped_column(ForeignKey("stages.stage_id"), primary_key=True)
    entry_id: Mapped[int] = mapped_column(ForeignKey("entries.entry_id"), primary_key=True)

    # Denormalized for query efficiency
    event_id: Mapped[int] = mapped_column(ForeignKey("events.event_id"))
    rally_id: Mapped[int] = mapped_column(ForeignKey("rallies.rally_id"))

    # Facts
    elapsed_duration_ms: Mapped[int | None]
    position: Mapped[int | None]
    diff_first_ms: Mapped[int | None]
    status: Mapped[StageStatus] = mapped_column(Enum(StageStatus))
```

### Pattern 2: State Snapshot Table

**Use for**: Evolving state (standings, rankings)

```python
class RallyStanding(Base):
    __tablename__ = "rally_standings"

    # Composite PK: (rally, stage, entry) = "standing after stage X"
    rally_id: Mapped[int] = mapped_column(primary_key=True)
    stage_id: Mapped[int] = mapped_column(primary_key=True)
    entry_id: Mapped[int] = mapped_column(primary_key=True)

    # State at this point
    position: Mapped[int | None]
    total_time_ms: Mapped[int]
    diff_first_ms: Mapped[int | None]
```

**Query**: "When did position change?"
```python
# Get consecutive standings
prev = select(RallyStanding).where(stage_id == N)
curr = select(RallyStanding).where(stage_id == N+1)
# Compare positions in application code
```

### Pattern 3: Hierarchical Denormalization

**Problem**: Deep hierarchy requires many joins

```
Event → Rally → Itinerary → Leg → Section → Stage
```

**Solution**: Add shortcut foreign keys

```python
class Stage(Base):
    stage_id: Mapped[int] = mapped_column(primary_key=True)

    # Direct parent (normalized)
    itinerary_section_id: Mapped[int] = mapped_column(ForeignKey(...))

    # Denormalized shortcuts
    event_id: Mapped[int] = mapped_column(ForeignKey("events.event_id"))
    rally_id: Mapped[int] = mapped_column(ForeignKey("rallies.rally_id"))
```

**Query**: "All stages in rally X" → `select(Stage).where(rally_id == X)` ✅ (no joins)

## Anti-Patterns

### ❌ Over-Normalization

```python
# Bad - forces 4 joins for "driver's stage times in rally"
class StageTime(Base):
    stage_id: Mapped[int]  # → Stage → Section → Leg → Itinerary → Event
    entry_id: Mapped[int]
```

**Fix**: Add `event_id`, `rally_id` directly.

### ❌ Premature Denormalization

```python
# Bad - adding field that's never queried directly
class StageTime(Base):
    stage_id: Mapped[int]
    itinerary_section_id: Mapped[int]  # ❌ Do we query by section? No.
```

**Fix**: Only denormalize for proven query patterns.

### ❌ Forgetting Composite Keys

```python
# Bad - allows duplicate (stage, entry) pairs
class StageTime(Base):
    id: Mapped[int] = mapped_column(primary_key=True)  # ❌ Synthetic ID
    stage_id: Mapped[int]
    entry_id: Mapped[int]
```

**Fix**: Use composite PK `(stage_id, entry_id)`.

### ❌ No Indexes

```python
# Bad - frequent filter on rally_id has no index
class StageTime(Base):
    rally_id: Mapped[int]  # ❌ Will be slow for large datasets
```

**Fix**: Add index: `Index('ix_stage_time_rally', 'rally_id')`.

## Checklist

Before finalizing schema:

- [ ] Each API model has a corresponding DB model
- [ ] Primary key strategy chosen (single vs composite)
- [ ] All query patterns tested (pseudocode joins)
- [ ] Denormalization applied for hot paths (join depth > 2)
- [ ] Enums used instead of strings for fixed values
- [ ] Indexes defined for frequent filters
- [ ] Foreign keys defined for referential integrity
- [ ] Nullable fields marked explicitly (`| None`)
- [ ] Composite PKs used for fact tables

## Example: Complete Model

```python
from enum import Enum as PyEnum
from sqlalchemy import String, ForeignKey, Enum, Index
from sqlalchemy.orm import Mapped, mapped_column
from .base import Base

class StageStatus(PyEnum):
    COMPLETED = "Completed"
    RETIRED = "Retired"
    DID_NOT_START = "DidNotStart"

class StageTime(Base):
    """Individual driver performance on a specific stage"""
    __tablename__ = "stage_times"

    # Composite PK
    stage_id: Mapped[int] = mapped_column(
        ForeignKey("stages.stage_id"),
        primary_key=True
    )
    entry_id: Mapped[int] = mapped_column(
        ForeignKey("entries.entry_id"),
        primary_key=True
    )

    # Denormalized for query efficiency
    event_id: Mapped[int] = mapped_column(ForeignKey("events.event_id"))
    rally_id: Mapped[int] = mapped_column(ForeignKey("rallies.rally_id"))

    # Measurements
    elapsed_duration_ms: Mapped[int | None]
    position: Mapped[int | None]
    diff_first_ms: Mapped[int | None]
    diff_prev_ms: Mapped[int | None]

    # Metadata
    status: Mapped[StageStatus] = mapped_column(Enum(StageStatus))
    source: Mapped[str] = mapped_column(String(50))

    # Indexes for common queries
    __table_args__ = (
        Index('ix_stage_time_rally_entry', 'rally_id', 'entry_id'),
        Index('ix_stage_time_stage', 'stage_id'),
    )
```

## Additional Resources

- For mapper implementation patterns, see your project's `storage/mappers.py`
- For query examples, see service layer implementations
