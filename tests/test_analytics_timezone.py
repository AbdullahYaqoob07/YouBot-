from datetime import datetime, timezone

from database.analytics import _utc_aware_datetime


def test_utc_aware_datetime_normalizes_naive_and_aware_values():
    naive_value = datetime(2026, 5, 1, 20, 24, 34, 872451)
    aware_value = datetime(2026, 5, 1, 20, 24, 34, 921812, tzinfo=timezone.utc)

    normalized_naive = _utc_aware_datetime(naive_value)
    normalized_aware = _utc_aware_datetime(aware_value)

    assert normalized_naive is not None
    assert normalized_naive.tzinfo == timezone.utc
    assert normalized_naive.hour == naive_value.hour
    assert normalized_aware == aware_value
