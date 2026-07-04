"""
convert split deltas into df for visualization for WRC data.
"""

import pandas as pd

from openwrc.services.read_models import FlatSplitTimeRow


def build_split_delta_df(rows: list[FlatSplitTimeRow]) -> pd.DataFrame:
    """Convert flat split time rows into a DataFrame enriched with delta-to-leader columns.

    Added columns:
        split_index  — 1-based physical ordering of split points, derived from
                       min elapsed time across entries (proxy for stage distance)
        split_label  — "SP1", "SP2", ... labels for display
        leader_ms    — fastest elapsed time at this split point across all entries
        delta_ms     — elapsed_duration_ms minus leader_ms (0 for the leader)

    Returns an empty DataFrame if rows is empty.
    """
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame([r.model_dump() for r in rows])

    # Order splits by their minimum elapsed time to approximate physical position
    split_order = (
        df.groupby("split_point_id")["elapsed_duration_ms"]
        .min()
        .sort_values()
        .reset_index()
        .assign(split_index=lambda x: range(1, len(x) + 1))
        .set_index("split_point_id")["split_index"]
        .to_dict()
    )
    df["split_index"] = df["split_point_id"].map(split_order)
    df["split_label"] = "SP" + df["split_index"].astype(str)

    # Delta to split leader
    df["leader_ms"] = df.groupby("split_point_id")["elapsed_duration_ms"].transform(
        "min"
    )
    df["delta_ms"] = df["elapsed_duration_ms"] - df["leader_ms"]

    return df.sort_values(["split_index", "delta_ms"])
