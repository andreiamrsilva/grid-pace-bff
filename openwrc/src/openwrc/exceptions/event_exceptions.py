class RallyNotFoundException(Exception):
    def __init__(self, rally_id: int, event_id: int, *args: object) -> None:
        message = f"Rally {rally_id} is not found in {event_id}"
        super().__init__(message, *args)


class StageNotFoundException(Exception):
    def __init__(
        self, rally_id: int, event_id: int, stage_id: int, *args: object
    ) -> None:
        message = f"Stage {stage_id} in rally {rally_id} is not found in {event_id}"
        super().__init__(message, *args)


class StageIndexOutOfRangeException(Exception):
    def __init__(self, rally_id: int, event_id: int, order: int, *args: object) -> None:
        message = f"Stage no. {order} in rally {rally_id} is not found in {event_id}"
        super().__init__(message, *args)


class StartListNotFoundException(Exception):
    def __init__(self, rally_id: int, event_id: int, order: int, *args: object) -> None:
        message = (
            f"Start list no. {order} in rally {rally_id} is not found in {event_id}"
        )
        super().__init__(message, *args)


class StartListNotAvailableYetException(Exception):
    def __init__(self, rally_id: int, event_id: int, order: int, *args: object) -> None:
        message = f"Start list no. {order} in rally {rally_id} is not available yet in {event_id}"
        super().__init__(message, *args)
