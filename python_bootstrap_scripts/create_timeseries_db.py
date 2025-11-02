#!/usr/bin/env python3
"""Create a time-series database for testing temporal analysis.

This creates a database with metrics over time, useful for testing
the summary agent's ability to detect trends and anomalies.
"""

import random
from datetime import datetime, timedelta
from pathlib import Path

import duckdb


def create_database(db_path: str = "data/sample_timeseries.duckdb"):
    """Create a time-series metrics database."""

    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    # Delete existing database if it exists
    db_file = Path(db_path)
    if db_file.exists():
        print(f"Removing existing database at: {db_path}")
        db_file.unlink()

    print(f"Creating time-series database at: {db_path}")
    conn = duckdb.connect(db_path)

    # Create tables
    print("Creating tables...")
    create_metrics_table(conn)
    create_events_table(conn)

    # Populate with data
    print("Populating metrics...")
    populate_metrics(conn, days=90)

    print("Populating events...")
    populate_events(conn, days=90)

    # Print summary
    print("\n" + "="*50)
    print("Time-series database created!")
    print("="*50)

    for table in ["daily_metrics", "system_events"]:
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"{table:20} {count:>6,} rows")

    print(f"\nDatabase location: {db_path}")
    print(f"Connection string: duckdb:///{db_path}")

    conn.close()


def create_metrics_table(conn):
    """Create daily metrics table."""
    conn.execute("""
        CREATE TABLE daily_metrics (
            metric_date DATE,
            active_users INTEGER,
            new_signups INTEGER,
            page_views INTEGER,
            revenue DECIMAL(10,2),
            avg_session_duration DECIMAL(10,2),
            error_rate DECIMAL(5,4),
            api_latency_ms DECIMAL(10,2)
        )
    """)


def create_events_table(conn):
    """Create system events table."""
    conn.execute("""
        CREATE TABLE system_events (
            event_id INTEGER PRIMARY KEY,
            event_timestamp TIMESTAMP,
            event_type VARCHAR,
            severity VARCHAR,
            source VARCHAR,
            message VARCHAR,
            user_id INTEGER
        )
    """)


def populate_metrics(conn, days: int):
    """Populate metrics with realistic time-series data."""
    start_date = datetime.now() - timedelta(days=days)

    metrics = []
    base_users = 10000
    base_pageviews = 50000
    base_revenue = 10000

    for day in range(days):
        date = start_date + timedelta(days=day)

        # Growth trend
        growth_factor = 1 + (day / days) * 0.2  # 20% growth over period

        # Weekly seasonality (weekends lower)
        is_weekend = date.weekday() >= 5
        weekend_factor = 0.7 if is_weekend else 1.0

        # Random variation
        daily_variation = random.uniform(0.9, 1.1)

        # Apply factors
        factor = growth_factor * weekend_factor * daily_variation

        active_users = int(base_users * factor)
        new_signups = int(active_users * random.uniform(0.02, 0.05))
        page_views = int(base_pageviews * factor)
        revenue = round(base_revenue * factor, 2)

        # Session duration (minutes)
        avg_session = round(random.uniform(3.5, 7.5), 2)

        # Introduce anomaly: sudden spike in errors around day 60
        if 58 <= day <= 62:
            error_rate = round(random.uniform(0.15, 0.25), 4)  # High error rate
        else:
            error_rate = round(random.uniform(0.001, 0.005), 4)  # Normal

        # API latency
        api_latency = round(random.uniform(80, 150), 2)

        # Introduce anomaly: latency spike around day 30
        if 28 <= day <= 32:
            api_latency = round(random.uniform(300, 500), 2)

        metrics.append((
            date.date(), active_users, new_signups, page_views, revenue,
            avg_session, error_rate, api_latency
        ))

    conn.executemany("""
        INSERT INTO daily_metrics VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, metrics)


def populate_events(conn, days: int):
    """Populate system events."""
    event_types = ["user_login", "user_logout", "api_call", "error", "warning", "deployment"]
    severities = ["info", "warning", "error", "critical"]
    sources = ["web_app", "api_server", "database", "cache", "worker"]

    start_date = datetime.now() - timedelta(days=days)

    events = []
    event_id = 1

    # Generate events throughout the period
    for day in range(days):
        date = start_date + timedelta(days=day)

        # Number of events per day varies
        num_events = random.randint(100, 500)

        # More errors during anomaly periods
        if 58 <= day <= 62 or 28 <= day <= 32:
            num_events = random.randint(800, 1200)

        for _ in range(num_events):
            # Random time during the day
            hour = random.randint(0, 23)
            minute = random.randint(0, 59)
            second = random.randint(0, 59)
            timestamp = date.replace(hour=hour, minute=minute, second=second)

            event_type = random.choice(event_types)

            # Severity distribution
            if event_type == "error":
                severity = random.choices(["error", "critical"], weights=[0.8, 0.2])[0]
            elif event_type == "warning":
                severity = "warning"
            else:
                severity = "info"

            source = random.choice(sources)

            # Generate message based on event type
            messages = {
                "user_login": "User logged in successfully",
                "user_logout": "User logged out",
                "api_call": f"API endpoint called: /api/v1/{random.choice(['users', 'orders', 'products'])}",
                "error": f"Error processing request: {random.choice(['timeout', 'connection_refused', 'validation_failed'])}",
                "warning": f"Warning: {random.choice(['high_memory_usage', 'slow_query', 'deprecated_api'])}",
                "deployment": f"Deployment completed: version {random.randint(1, 10)}.{random.randint(0, 20)}.{random.randint(0, 50)}"
            }
            message = messages[event_type]

            user_id = random.randint(1, 1000) if event_type in ["user_login", "user_logout"] else None

            events.append((
                event_id, timestamp, event_type, severity, source, message, user_id
            ))
            event_id += 1

    conn.executemany("""
        INSERT INTO system_events VALUES (?, ?, ?, ?, ?, ?, ?)
    """, events)


if __name__ == "__main__":
    create_database()
