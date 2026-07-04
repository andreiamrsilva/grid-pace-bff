from datetime import datetime


class SessionInputValidationException(Exception):
    def __init__(self, message: str, *args: object) -> None:
        super().__init__(message, *args)


class SessionDateOutOfRangeException(Exception):
    def __init__(
        self,
        current_time: datetime,
        start_date: datetime,
        finish_date: datetime,
        *args: object,
    ) -> None:
        message = (
            f"Current time {current_time.isoformat()} is outside event date range "
            f"({start_date.isoformat()} to {finish_date.isoformat()})"
        )
        super().__init__(message, *args)
