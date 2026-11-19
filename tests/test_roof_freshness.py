from datetime import datetime, timedelta

from modules.roof_freshness import (
    roof_status_age_seconds,
    roof_status_is_stale,
)


now = datetime(2026, 8, 8, 12, 0, 0)

fresh_timestamp = now - timedelta(seconds=30)
stale_timestamp = now - timedelta(minutes=10)

threshold = 60

fresh_age = roof_status_age_seconds(
    fresh_timestamp,
    now=now,
)

stale_age = roof_status_age_seconds(
    stale_timestamp,
    now=now,
)

print(f"Fresh age: {fresh_age} seconds")
print(f"Fresh stale? {roof_status_is_stale(fresh_timestamp, threshold, now)}")

print(f"Stale age: {stale_age} seconds")
print(f"Stale stale? {roof_status_is_stale(stale_timestamp, threshold, now)}")