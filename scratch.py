from datetime import datetime, date, timedelta, timezone

def test():
    now = datetime.now(timezone.utc)
    print(now)

test()
