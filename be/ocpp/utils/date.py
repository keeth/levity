from datetime import datetime


def isoformat(dt: datetime):
    return dt.isoformat().replace("+00:00", "Z")
