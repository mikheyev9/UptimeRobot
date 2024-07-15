from datetime import datetime, timedelta, timezone

def calculate_downtime(down_since: dict, url) -> str:
    downtime = datetime.now(timezone.utc) - down_since.get(url, datetime.now(timezone.utc))
    if downtime < timedelta(0):
        downtime = timedelta(0)
    return str(downtime).split('.')[0]
