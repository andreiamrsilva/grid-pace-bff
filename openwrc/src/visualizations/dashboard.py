"""
WRC Dashboard — Streamlit

Run with:
    streamlit run src/visualizations/dashboard.py
"""

import asyncio
import logging
import os

import pandas as pd

if os.getenv("WRC_DEBUG_SQL", "").lower() in ("1", "true", "yes"):
    logging.getLogger("openwrc.db").setLevel(logging.DEBUG)
    logging.getLogger("openwrc.db").addHandler(logging.StreamHandler())
import plotly.express as px
import streamlit as st

from openwrc.services.session_service import WrcSession
from visualizations.split_deltas import build_split_delta_df


# ---------------------------------------------------------------------------
# Data loading — each function creates a fresh async session inside
# asyncio.run() so Streamlit's sync context and the async DB layer don't clash.
# @st.cache_data memoises by args so re-renders don't re-query.
# ---------------------------------------------------------------------------


@st.cache_data
def _load_years() -> list[int]:
    return asyncio.run(WrcSession.list_available_years())


@st.cache_data
def _load_events(year: int) -> list:
    return asyncio.run(WrcSession.list_events_for_year(year=year))


@st.cache_data
def _load_standings(event_id: int) -> pd.DataFrame:
    async def _fetch():
        session = await WrcSession.create(event_id=event_id)
        return await session.flat_standings()

    rows = asyncio.run(_fetch())
    return pd.DataFrame([r.model_dump() for r in rows])


@st.cache_data
def _load_split_times(event_id: int, stage_id: int) -> list:
    async def _fetch():
        session = await WrcSession.create(event_id=event_id)
        return await session.flat_split_times(stage_id=stage_id)

    return asyncio.run(_fetch())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ms_to_mmss(ms: int | float | None, signed: bool = False) -> str:
    """Format milliseconds as m:ss.t (tenths precision)."""
    if ms is None or (isinstance(ms, float) and pd.isna(ms)):
        return "—"
    ms = int(ms)
    sign = ("+" if ms > 0 else "") if signed else ""
    abs_ms = abs(ms)
    minutes = abs_ms // 60_000
    seconds = (abs_ms % 60_000) // 1_000
    tenths = (abs_ms % 1_000) // 100
    return f"{sign}{minutes}:{seconds:02d}.{tenths}"


def _time_axis_ticks(series: pd.Series, n: int = 8) -> tuple[list[float], list[str]]:
    """Generate n evenly-spaced tick values and mm:ss.t labels for a time (ms) axis."""
    lo, hi = series.min(), series.max()
    if pd.isna(lo) or pd.isna(hi) or lo == hi:
        return [], []
    step = (hi - lo) / (n - 1)
    vals = [lo + i * step for i in range(n)]
    return vals, [_ms_to_mmss(v) for v in vals]


_METRIC_OPTIONS: dict[str, str] = {
    "Gap to first": "diff_first_ms",
    "Overall position": "position",
    "Total time": "total_time_ms",
    "Stage time": "stage_time_ms",
}

_TIME_METRICS = {"diff_first_ms", "total_time_ms", "stage_time_ms"}


def _class_driver_selectors(df: pd.DataFrame, key_prefix: str) -> tuple[str, list[str]]:
    """Render class + driver multiselect controls, where driver list is scoped to class.

    Returns (selected_class, selected_drivers).
    """
    classes = sorted(df["class_name"].dropna().unique())
    selected_class = st.selectbox("Class", ["All"] + classes, key=f"{key_prefix}_class")
    drivers_in_class = sorted(
        df.loc[df["class_name"] == selected_class, "driver_name"].unique()
        if selected_class != "All"
        else df["driver_name"].unique()
    )
    selected_drivers = st.multiselect(
        "Drivers",
        drivers_in_class,
        placeholder="All drivers",
        key=f"{key_prefix}_drivers",
    )
    return selected_class, selected_drivers


def _ordered_stage_codes(df: pd.DataFrame) -> list[str]:
    return (
        df[["stage_number", "stage_code"]]
        .drop_duplicates()
        .sort_values("stage_number")["stage_code"]
        .tolist()
    )


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

st.set_page_config(page_title="WRC Dashboard", layout="wide", page_icon="🏁")
st.title("WRC Dashboard")

# ---- Sidebar: event selection ----
with st.sidebar:
    st.header("Event")
    years = _load_years()
    year = st.selectbox("Year", years, index=len(years) - 1)

    events = _load_events(year)
    if not events:
        st.warning("No events found for this year.")
        st.stop()

    event_map = {f"{e.name}  ({e.location})": e for e in events}
    event_label = st.selectbox("Event", list(event_map.keys()))
    event = event_map[event_label]

event_id = event.event_id
df_standings = _load_standings(event_id)

if df_standings.empty:
    st.warning("No standings data for this event yet — run the ETL first.")
    st.stop()

stage_order = _ordered_stage_codes(df_standings)
all_drivers = sorted(df_standings["driver_name"].unique())

tab_standings, tab_splits = st.tabs(["📈 Standings Progression", "⏱️ Stage Split Times"])


# ---------------------------------------------------------------------------
# Tab 1 — Standings Progression
# ---------------------------------------------------------------------------

with tab_standings:
    ctrl, chart_col = st.columns([1, 4])

    with ctrl:
        metric_label = st.selectbox("Metric", list(_METRIC_OPTIONS.keys()))
        metric_field = _METRIC_OPTIONS[metric_label]
        selected_class, selected_drivers = _class_driver_selectors(
            df_standings, "standings"
        )
        stage_range = st.select_slider(
            "Stage range",
            options=stage_order,
            value=(stage_order[0], stage_order[-1]),
        )

    df = df_standings.copy()
    if selected_drivers:
        df = df[df["driver_name"].isin(selected_drivers)]
    if selected_class != "All":
        df = df[df["class_name"] == selected_class]
    start_idx = stage_order.index(stage_range[0])
    end_idx = stage_order.index(stage_range[1])
    df = df[df["stage_code"].isin(stage_order[start_idx : end_idx + 1])]

    df["stage_code"] = pd.Categorical(
        df["stage_code"], categories=stage_order, ordered=True
    )
    df = df.sort_values(["stage_number", "position"])

    with chart_col:
        if df.empty:
            st.info("No data for the selected filters.")
        else:
            is_time = metric_field in _TIME_METRICS
            if is_time:
                df["_time_label"] = df[metric_field].apply(_ms_to_mmss)

            fig = px.line(
                df,
                x="stage_code",
                y=metric_field,
                color="driver_name",
                markers=True,
                title=f"{metric_label} — Stage Progression",
                labels={
                    "stage_code": "Stage",
                    metric_field: metric_label,
                    "driver_name": "Driver",
                },
                custom_data=(
                    ["driver_name", "_time_label"] if is_time else ["driver_name"]
                ),
                color_discrete_sequence=px.colors.qualitative.Set2,
            )
            if metric_field == "position":
                fig.update_yaxes(autorange="reversed", dtick=1, title="Position")
                fig.update_traces(
                    hovertemplate="<b>%{customdata[0]}</b>: P%{y}<extra></extra>"
                )
            elif is_time:
                tick_vals, tick_text = _time_axis_ticks(df[metric_field].dropna())
                invert = metric_field == "diff_first_ms"
                fig.update_yaxes(
                    tickvals=tick_vals,
                    ticktext=tick_text,
                    title=metric_label,
                    autorange="reversed" if invert else True,
                )
                fig.update_traces(
                    hovertemplate="<b>%{customdata[0]}</b>: %{customdata[1]}<extra></extra>"
                )
            fig.update_layout(
                height=500, legend_title_text="Driver", hovermode="x unified"
            )
            st.plotly_chart(fig, width="stretch")

    with st.expander("Data table"):
        display_cols = [
            "stage_code",
            "driver_name",
            "car_number",
            "manufacturer_name",
            "class_name",
            "position",
            "diff_first_ms",
            "total_time_ms",
            "stage_time_ms",
        ]
        display_df = df[display_cols].sort_values(["stage_code", "position"]).copy()
        for col in ("diff_first_ms", "total_time_ms", "stage_time_ms"):
            display_df[col] = display_df[col].apply(
                lambda v: _ms_to_mmss(v, signed=(col == "diff_first_ms"))
            )
        st.dataframe(display_df, width="stretch", hide_index=True)


# ---------------------------------------------------------------------------
# Tab 2 — Stage Split Times
# ---------------------------------------------------------------------------

with tab_splits:
    ctrl2, chart_col2 = st.columns([1, 4])

    with ctrl2:
        selected_stage_code = st.selectbox("Stage", stage_order)
        selected_split_class, selected_drivers_split = _class_driver_selectors(
            df_standings, "splits"
        )

    stage_id = int(
        df_standings.loc[
            df_standings["stage_code"] == selected_stage_code, "stage_id"
        ].iloc[0]
    )
    split_rows = _load_split_times(event_id, stage_id)
    df_splits = build_split_delta_df(split_rows)

    with chart_col2:
        if df_splits.empty:
            st.info("No split time data for this stage.")
        else:
            df_filtered = df_splits.copy()
            if selected_drivers_split:
                df_filtered = df_filtered[
                    df_filtered["driver_name"].isin(selected_drivers_split)
                ]
            if selected_split_class != "All":
                df_filtered = df_filtered[
                    df_filtered["class_name"] == selected_split_class
                ]
            df_splits = df_filtered

            df_splits["_delta_label"] = df_splits["delta_ms"].apply(
                lambda v: _ms_to_mmss(v, signed=True)
            )

            fig2 = px.line(
                df_splits.sort_values("split_index"),
                x="split_label",
                y="delta_ms",
                color="driver_name",
                markers=True,
                title=f"Cumulative Split Delta to Leader — {selected_stage_code}",
                labels={
                    "split_label": "Split Point",
                    "delta_ms": "Delta",
                    "driver_name": "Driver",
                },
                custom_data=["driver_name", "_delta_label"],
                color_discrete_sequence=px.colors.qualitative.Set2,
            )
            tick_vals2, tick_text2 = _time_axis_ticks(df_splits["delta_ms"].dropna())
            fig2.update_yaxes(
                tickvals=tick_vals2,
                ticktext=tick_text2,
                title="Delta to Leader",
                autorange="reversed",
            )
            fig2.update_traces(
                hovertemplate="<b>%{customdata[0]}</b>: %{customdata[1]}<extra></extra>"
            )
            fig2.update_layout(
                height=500, legend_title_text="Driver", hovermode="x unified"
            )
            st.plotly_chart(fig2, width="stretch")

    with st.expander("Data table"):
        if not df_splits.empty:
            display_split = (
                df_splits[
                    [
                        "split_label",
                        "driver_name",
                        "car_number",
                        "elapsed_duration_ms",
                        "delta_ms",
                    ]
                ]
                .sort_values(["split_label", "delta_ms"])
                .copy()
            )
            display_split["elapsed_duration_ms"] = display_split[
                "elapsed_duration_ms"
            ].apply(_ms_to_mmss)
            display_split["delta_ms"] = display_split["delta_ms"].apply(
                lambda v: _ms_to_mmss(v, signed=True)
            )
            display_split.columns = ["Split", "Driver", "Car", "Elapsed", "Delta"]
            st.dataframe(display_split, width="stretch", hide_index=True)
