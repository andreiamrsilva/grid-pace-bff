from pydantic import BaseModel

from openwrc.models.external_api import ApiStageResults


class CumulativeStageResults(BaseModel):
    stage_id: int
    results: ApiStageResults


class CumulativeRallyResultsByStage(BaseModel):
    event_id: int
    rally_id: int
    cumulative_stage_results: list[CumulativeStageResults]
