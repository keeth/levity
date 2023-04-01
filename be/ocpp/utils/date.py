from datetime import datetime, timezone


def iso_format(dt: datetime):
    return dt.isoformat().replace("+00:00", "Z")


def utc_now():
    return datetime.now(timezone.utc)
