# agentic layer for smart querying and visualization

## goal

I'm no motorsport analyst or expert. i have random questions i'd like to ask every now and then when i watch the events. for example
- where did Elfyn Evans lose time to Seb Ogier during Rally Saudi Arabia 2025? how did the point tally swing between those 2 as the stage went on?
- when the live timing comes in during a stage, what is the gap between the current driver to the leader? if they match pace for pace for the rest of the stage, what does the standings look like?
- is hyundai actually struggling for pace over the past few seasons? when were they competitive, and what is the trend compared to toyota?

Now that this project acts as a data sink, we can think about on-the-fly analytics and visualization generation via agents. This is to define the action space of the agent, and understand what is needed for the workflow of the agents to get the relevant info.

## challenges

tldr: i'm not an expert lol so i'm not gonna be able to work at the right level of abstraction at all times

- I don't really have a clear idea what is needed for these queries to be answered. I have a *general* idea, but you know i'd probably have to go in and work a few examples to figure out what exactly is needed
- if I don't have that idea, I just let the agent loose, they agent can probably do a decent job. but is that the optimal way to query? I'd have to judgement power at all.
- i'd love to break things down into smaller building blocks so we can uncover common query patterns and make these as reuseable as possible. that way we don't have to rebuild the wheel every single time, and we define more concrete action set for the agent to build off of.

## thoughts on these building blocks

### Scope of the query
what is the scope of the query? this scope can be two dimensional, almost like a break down to slice the data

- break down on entry entities: are we talking about a team, a car make, a driver?
- break down on span in the event: what is the scope in terms of race entities? is it about an entire rally, a single stage, split points, or trends over the years?

### Visualization

what kind of graphs help deliver the insight i want?

- i'd imagine most are gonna be timeseries graphs to show progression in the right span. x axis would be the granularity of the break down, from rally, stage, split point, etc.
- some might just be live leaderboards if i want to pipe in live data
- idk what else for now

### explanation

if we are looking for aggregate insights, some sort of data summary would be amazing

- the agent is able to view the trends in data, or devise procedures to uncover trends in the data
- use both visualization and language to respond to questions

### how to resolve filters?

i mean different filters will mean different join paths,
- we need to find the right entry ids given the filters. that's what gives us the lowest granularity results metrics
- we need to find the right aggregations to meaningfully aggregate the metrics. so do we need to aggregate back to the manufacturer, team, etc?
this mapping space seems large, idk how to resolve them generally

---

## two modes of querying

### progression mode (primary target)

most fan questions are fundamentally about **progression** — how did something change over a span? these map cleanly onto a time series: x axis is a span granularity, each line is a queried entity, y axis is the metric.

the structural choice space is low cardinality and can be exposed directly as a UI:

```
span granularity:  [ split | stage | leg | rally | season ]
entity level:      [ class | manufacturer | entrant | car | driver | codriver ]
metric:            [ stage time | gap to first | position | pace | cumulative time ]
filters:           pin specific values (rally, year, driver names, etc.)
```

output is always a time series of shape `(entity_label, span_label, span_order, metric_value)`.

the agent's only role in this mode is **entity resolution** — mapping filter inputs like "Evans" or "Saudi 2025" to concrete DB ids. the structure of the query is determined by the UI, not the agent.

### analytics mode (out of scope for now)

some questions aren't about progression — they're about correlation, distribution, or comparing across a non-span axis like surface type or road position. for example:
- does road position (first on road vs later) systematically cost time on gravel?
- how does toyota's pace compare on gravel vs tarmac vs snow?
- what's the distribution of stage win margins?

these are harder for two reasons:
1. the query structure is not obvious — there are multiple valid ways to frame the question and multiple valid proxies to measure
2. each question needs a **methodology decision** first (what's the right proxy? what's the confound?) before it can be turned into a query

analytics mode questions are best treated as named, hand-crafted templates worked out one at a time rather than auto-generated from a query builder. they're left for later.

## dimensions

every query slices data along dimensions. a dimension's role (x-axis, series/groupby, or filter) is decided at query time — not fixed to the dimension itself.

**span dimensions** (natural x-axis candidates — ordered progressions):
- `split_point` → `stage` → `leg/day` → `rally` → `season`

**entity dimensions** (natural series/groupby candidates — things you compare):
- `class` → `manufacturer` → `entrant` → `car` → `driver` → `codriver`

**condition dimensions** (almost always filters in progression mode):
- surface type (gravel / tarmac / snow) — *note: currently only stored at event level, not per stage*
- stage type (standard / super special stage)
- stage distance
- road position / start order
- country / location

## schema gaps worth noting

- `SplitPoint` table doesn't exist yet — `SplitTime.split_point_id` is an orphan FK with no distance or order metadata, which means split-level x-axis labels are meaningless until this is added
- per-stage surface type is missing — `surfaces` is only on `EventMetadata`, so gravel/tarmac filters can't be applied at stage granularity for mixed-surface events
- cross-rally driver identity requires joining `Entry.driver_id → Person` across multiple rallies, since `Entry` is scoped per rally — query layer needs to handle this grouping explicitly for season-level trends
- championship points are not stored — season-level "who's winning the championship" queries require either a points calculation layer or a separate table

## next steps

- [ ] build progression mode interactive UI (3 dropdowns + filter inputs + chart output)
- [ ] entity resolution: autocomplete/lookup for filter inputs against the DB
- [ ] analytics mode: work out methodology for road position effect, surface performance comparison, etc. one template at a time
