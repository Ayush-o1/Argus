"""Unit tests for the pure statistical helpers in app/services/anomaly.py.

The Isolation Forest path needs a live Neo4j graph to build its feature
matrix, but the sliding-window burst counter and z-score are plain math and
worth pinning directly — a regression here would silently change which
accounts get flagged as anomalous.
"""

from datetime import datetime, timedelta

from app.services.anomaly import _max_burst_count, _zscore


def test_max_burst_count_empty():
    assert _max_burst_count([], window_seconds=3600) == 0


def test_max_burst_count_single_timestamp():
    assert _max_burst_count([datetime(2024, 1, 1, 12, 0)], window_seconds=3600) == 1


def test_max_burst_count_all_within_window():
    base = datetime(2024, 1, 1, 12, 0)
    timestamps = [base + timedelta(minutes=i) for i in range(5)]
    assert _max_burst_count(timestamps, window_seconds=3600) == 5


def test_max_burst_count_finds_densest_window():
    base = datetime(2024, 1, 1, 0, 0)
    # A dense burst of 4 within 1 hour, then isolated events spread far apart.
    burst = [base + timedelta(minutes=i * 10) for i in range(4)]
    scattered = [base + timedelta(hours=h) for h in (10, 20, 30)]
    timestamps = burst + scattered
    assert _max_burst_count(timestamps, window_seconds=3600) == 4


def test_max_burst_count_ignores_input_order():
    base = datetime(2024, 1, 1, 0, 0)
    timestamps = [base + timedelta(minutes=30), base, base + timedelta(minutes=15)]
    assert _max_burst_count(timestamps, window_seconds=3600) == 3


def test_zscore_at_mean_is_zero():
    assert _zscore(50.0, mean=50.0, std=10.0) == 0.0


def test_zscore_positive_and_negative():
    assert _zscore(70.0, mean=50.0, std=10.0) == 2.0
    assert _zscore(30.0, mean=50.0, std=10.0) == -2.0


def test_zscore_zero_std_returns_zero():
    """A degenerate population (every account identical) must not divide by zero."""
    assert _zscore(50.0, mean=50.0, std=0.0) == 0.0
