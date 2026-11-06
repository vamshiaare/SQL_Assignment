# I use built-in packages, so no installation is required.
import sqlite3
import random
from pathlib import Path
from datetime import datetime, timedelta

rng = random.Random(42)
db_path = Path("electric_bicycle_fleet.db")

# Rerunning replaces only this generated database.
if db_path.exists():
    db_path.unlink()

conn = sqlite3.connect(db_path)
conn.execute("PRAGMA foreign_keys = ON")

# ==========================================================
# 1. DATABASE STRUCTURE
# ==========================================================
# Nominal: bicycle_type.
# Ordinal: maintenance_priority: Low < Medium < High < Critical.
# Interval: battery_temperature_c.
# Ratio: journey_distance_km, duration_minutes, repair_cost.
# All repair costs are in GBP; timestamps use one local time basis.
#
# This models a small fleet with intermittent recorded journeys.
# It does not claim to represent a complete commercial hire service.

conn.executescript("""
CREATE TABLE stations (
    station_id INTEGER PRIMARY KEY,
    station_name TEXT NOT NULL UNIQUE,
    area_type TEXT NOT NULL
        CHECK (area_type IN ('Residential', 'Commercial', 'Transport')),
    docking_capacity INTEGER NOT NULL
        CHECK (docking_capacity BETWEEN 10 AND 50)
);

CREATE TABLE bicycles (
    bicycle_id INTEGER PRIMARY KEY,
    frame_code TEXT NOT NULL UNIQUE,
    bicycle_type TEXT NOT NULL
        CHECK (bicycle_type IN ('City', 'Folding', 'Cargo')),
    commissioned_on TEXT NOT NULL
        CHECK (date(commissioned_on, '+0 days') IS NOT NULL
           AND date(commissioned_on, '+0 days') = commissioned_on),
    service_status TEXT NOT NULL
        CHECK (service_status IN ('Available', 'Maintenance', 'Retired'))
);

CREATE TABLE batteries (
    battery_id INTEGER PRIMARY KEY,
    serial_number TEXT NOT NULL UNIQUE,
    capacity_wh INTEGER NOT NULL
        CHECK (capacity_wh IN (400, 500, 625)),
    commissioned_on TEXT NOT NULL
        CHECK (date(commissioned_on, '+0 days') IS NOT NULL
           AND date(commissioned_on, '+0 days') = commissioned_on),
    battery_status TEXT NOT NULL
        CHECK (battery_status IN ('In service', 'Spare', 'Retired'))
);

CREATE TABLE battery_assignments (
    bicycle_id INTEGER NOT NULL,
    installed_at TEXT NOT NULL
        CHECK (datetime(installed_at, '+0 seconds') IS NOT NULL
           AND datetime(installed_at, '+0 seconds') = installed_at),
    battery_id INTEGER NOT NULL,
    removed_at TEXT NOT NULL
        CHECK (datetime(removed_at, '+0 seconds') IS NOT NULL
           AND datetime(removed_at, '+0 seconds') = removed_at),
    initial_charge_pct REAL NOT NULL
        CHECK (initial_charge_pct BETWEEN 0 AND 100),

    PRIMARY KEY (bicycle_id, installed_at),
    FOREIGN KEY (bicycle_id) REFERENCES bicycles(bicycle_id),
    FOREIGN KEY (battery_id) REFERENCES batteries(battery_id),
    CHECK (removed_at > installed_at)
);

CREATE TABLE journeys (
    journey_id INTEGER PRIMARY KEY,
    bicycle_id INTEGER NOT NULL,
    installed_at TEXT NOT NULL,
    start_station_id INTEGER NOT NULL,
    end_station_id INTEGER NOT NULL,
    departure_at TEXT NOT NULL
        CHECK (datetime(departure_at, '+0 seconds') IS NOT NULL
           AND datetime(departure_at, '+0 seconds') = departure_at),
    arrival_at TEXT NOT NULL
        CHECK (datetime(arrival_at, '+0 seconds') IS NOT NULL
           AND datetime(arrival_at, '+0 seconds') = arrival_at),
    journey_distance_km REAL NOT NULL
        CHECK (journey_distance_km > 0 AND journey_distance_km <= 30),
    duration_minutes REAL NOT NULL
        CHECK (duration_minutes > 0 AND duration_minutes <= 180),
    start_charge_pct REAL NOT NULL
        CHECK (start_charge_pct BETWEEN 0 AND 100),
    end_charge_pct REAL NOT NULL
        CHECK (end_charge_pct BETWEEN 0 AND 100),
    battery_temperature_c REAL
        CHECK (battery_temperature_c IS NULL
           OR battery_temperature_c BETWEEN -10 AND 60),

    FOREIGN KEY (bicycle_id, installed_at)
        REFERENCES battery_assignments(bicycle_id, installed_at),
    FOREIGN KEY (start_station_id) REFERENCES stations(station_id),
    FOREIGN KEY (end_station_id) REFERENCES stations(station_id),

    CHECK (arrival_at > departure_at),
    CHECK (end_charge_pct <= start_charge_pct),
    CHECK (
        ABS((julianday(arrival_at) - julianday(departure_at)) * 1440
            - duration_minutes) < 0.001
    ),
    CHECK (journey_distance_km / duration_minutes * 60 BETWEEN 5 AND 30)
);

CREATE TABLE maintenance_jobs (
    job_id INTEGER PRIMARY KEY,
    bicycle_id INTEGER NOT NULL,
    station_id INTEGER NOT NULL,
    maintenance_priority TEXT NOT NULL
        CHECK (maintenance_priority IN ('Low', 'Medium', 'High', 'Critical')),
    fault_category TEXT NOT NULL
        CHECK (fault_category IN
            ('Brakes', 'Tyres', 'Drivetrain', 'Electrical')),
    opened_at TEXT NOT NULL
        CHECK (datetime(opened_at, '+0 seconds') IS NOT NULL
           AND datetime(opened_at, '+0 seconds') = opened_at),
    completed_at TEXT
        CHECK (completed_at IS NULL OR (
            datetime(completed_at, '+0 seconds') IS NOT NULL
            AND datetime(completed_at, '+0 seconds') = completed_at
            AND completed_at > opened_at
        )),
    job_notes TEXT
        CHECK (job_notes IS NULL OR length(trim(job_notes)) > 0),

    FOREIGN KEY (bicycle_id) REFERENCES bicycles(bicycle_id),
    FOREIGN KEY (station_id) REFERENCES stations(station_id)
);

CREATE TABLE maintenance_tasks (
    job_id INTEGER NOT NULL,
    task_number INTEGER NOT NULL CHECK (task_number > 0),
    task_description TEXT NOT NULL
        CHECK (length(trim(task_description)) > 0),
    labour_minutes INTEGER NOT NULL
        CHECK (labour_minutes BETWEEN 5 AND 180),
    repair_cost REAL NOT NULL
        CHECK (repair_cost BETWEEN 0 AND 500),

    PRIMARY KEY (job_id, task_number),
    FOREIGN KEY (job_id) REFERENCES maintenance_jobs(job_id)
);
""")

# ==========================================================
# 2. STATIONS, BICYCLES AND BATTERIES
# ==========================================================
station_names = [
    "Riverside", "Market Square", "Central Station", "Oak Park",
    "University Gate", "Civic Centre", "West Gardens", "North Hub",
    "Library Square", "East Market", "South Station", "Canal Walk"
]

stations = [
    (
        i, name,
        ["Residential", "Commercial", "Transport"][(i - 1) % 3],
        rng.choice([20, 24, 30])
    )
    for i, name in enumerate(station_names, start=1)
]

conn.executemany(
    "INSERT INTO stations VALUES (?, ?, ?, ?)", stations
)

bicycles = []
bike_types = {}

for bicycle_id in range(1, 81):
    bicycle_type = rng.choices(
        ["City", "Folding", "Cargo"], weights=[65, 25, 10]
    )[0]
    bike_types[bicycle_id] = bicycle_type

    bicycles.append((
        bicycle_id, f"EB-{bicycle_id:04d}", bicycle_type,
        "2024-06-01", "Available"
    ))

conn.executemany(
    "INSERT INTO bicycles VALUES (?, ?, ?, ?, ?)", bicycles
)

# There are 80 operational batteries and 20 reserve batteries.
batteries = [
    (
        battery_id,
        f"BAT-{battery_id:05d}",
        rng.choice([400, 500, 625]),
        "2024-06-01",
        "In service" if battery_id <= 80 else "Spare"
    )
    for battery_id in range(1, 101)
]

conn.executemany(
    "INSERT INTO batteries VALUES (?, ?, ?, ?, ?)", batteries
)

battery_capacity = {row[0]: row[2] for row in batteries}

# ==========================================================
# 3. BUILD CONNECTED OPERATING HISTORIES
# ==========================================================
# Each bike has three consecutive 120-day battery assignments.
# Batteries rotate between bikes at the assignment boundaries.
# The rotation is a permutation: no battery is installed on two
# bicycles at the same time.
#
# Replacement batteries begin fully charged. During an assignment
# charge only decreases; no unrecorded charging is assumed.
#
# Each bicycle makes 19 journeys: 7, 6 and 6 across the periods.
# Maintenance is scheduled after journeys in the first two periods.
start_date = datetime(2025, 1, 1)
fmt = "%Y-%m-%d %H:%M:%S"

assignments = []
journeys = []
jobs = []
tasks = []

current_station = {
    bicycle_id: (bicycle_id - 1) % 12 + 1
    for bicycle_id in range(1, 81)
}

task_catalogue = {
    "Brakes": [
        ("Brake inspection and adjustment", 25, 5),
        ("Brake pad replacement", 35, 18)
    ],
    "Tyres": [
        ("Tyre and pressure inspection", 15, 0),
        ("Inner tube replacement", 25, 9)
    ],
    "Drivetrain": [
        ("Chain cleaning and lubrication", 20, 4),
        ("Gear adjustment", 25, 2)
    ],
    "Electrical": [
        ("Electrical connection inspection", 30, 2),
        ("Sensor adjustment", 35, 7)
    ]
}

journey_id = 0
job_id = 0

for period in range(3):
    installed = start_date + timedelta(days=period * 120)
    removed = installed + timedelta(days=120)

    for bicycle_id in range(1, 81):
        battery_id = (bicycle_id - 1 + period * 17) % 80 + 1
        installed_text = installed.strftime(fmt)

        assignments.append((
            bicycle_id, installed_text, battery_id,
            removed.strftime(fmt), 100.0
        ))

        charge = 100.0
        trip_count = [7, 6, 6][period]

        for trip in range(trip_count):
            journey_id += 1
            origin = current_station[bicycle_id]

            # A modest proportion of journeys return to the same station.
            if rng.random() < 0.12:
                destination = origin
            else:
                destination = rng.choice([
                    sid for sid in range(1, 13) if sid != origin
                ])

            # Distances are synthetic route lengths, not geographic claims.
            distance = round(rng.triangular(0.8, 8.0, 2.5), 2)
            typical_speed = {
                "City": 17, "Folding": 15, "Cargo": 13
            }[bike_types[bicycle_id]]

            speed = max(8, min(24, rng.gauss(typical_speed, 1.5)))
            minutes = max(4, round(distance / speed * 60))

            departure = installed + timedelta(
                days=3 + trip * 12,
                hours=8 + (bicycle_id % 10),
                minutes=rng.randrange(60)
            )
            arrival = departure + timedelta(minutes=minutes)

            energy_wh = (
                distance
                * {"City": 8, "Folding": 8.5, "Cargo": 11}[
                    bike_types[bicycle_id]
                ]
                * rng.uniform(0.9, 1.1)
            )
            end_charge = round(
                charge - energy_wh / battery_capacity[battery_id] * 100, 2
            )
            assert end_charge >= 0

            temperature = round(
                19
                + energy_wh * 0.08
                + rng.gauss(0, 1.2), 1
            )

            journeys.append((
                journey_id, bicycle_id, installed_text,
                origin, destination,
                departure.strftime(fmt), arrival.strftime(fmt),
                distance, minutes, charge, end_charge, temperature
            ))

            charge = end_charge
            current_station[bicycle_id] = destination

        # All 160 jobs are completed before the next period.
        if period < 2:
            job_id += 1

            fault = rng.choices(
                list(task_catalogue), weights=[30, 30, 25, 15]
            )[0]
            priority = rng.choices(
                ["Low", "Medium", "High", "Critical"],
                weights=[25, 50, 20, 5]
            )[0]

            opened = installed + timedelta(days=100, hours=9)
            hours_required = {
                "Low": 4, "Medium": 6, "High": 8, "Critical": 10
            }[priority]
            completed = opened + timedelta(hours=hours_required)

            jobs.append((
                job_id, bicycle_id, current_station[bicycle_id],
                priority, fault,
                opened.strftime(fmt), completed.strftime(fmt),
                "Completed service; bicycle returned to availability"
            ))

            # One or two fault-specific tasks per job.
            selected_tasks = task_catalogue[fault][
                :rng.choices([1, 2], weights=[35, 65])[0]
            ]

            for task_number, (description, base_minutes, parts) in enumerate(
                selected_tasks, start=1
            ):
                labour = max(5, base_minutes + rng.randint(-5, 10))

                # Cost relates to labour and parts instead of being unrelated.
                cost = round(
                    labour / 60 * 30 + parts * rng.uniform(0.9, 1.1), 2
                )

                tasks.append((
                    job_id, task_number, description, labour, cost
                ))

conn.executemany(
    "INSERT INTO battery_assignments VALUES (?, ?, ?, ?, ?)",
    assignments
)

# ==========================================================
# 4. DELIBERATELY INSERT MISSING VALUES
# ==========================================================
# Exactly 76 journey temperature readings are missing:
# 76 / 1,520 = 5%. Essential journey details remain complete.
for index in rng.sample(range(len(journeys)), 76):
    row = list(journeys[index])
    row[11] = None
    journeys[index] = tuple(row)

# Exactly 16 maintenance notes are missing: 16 / 160 = 10%.
for index in rng.sample(range(len(jobs)), 16):
    row = list(jobs[index])
    row[7] = None
    jobs[index] = tuple(row)

conn.executemany(
    "INSERT INTO journeys VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
    journeys
)
conn.executemany(
    "INSERT INTO maintenance_jobs VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
    jobs
)

# ==========================================================
# 5. DELIBERATELY INSERT DUPLICATE BUSINESS RECORDS
# ==========================================================
# A duplicate task matches job, description, labour and cost,
# while using a different task_number.
# These are repeated entries, not additional work performed.
original_task_count = len(tasks)
copies = []

for selected_job in rng.sample(range(1, 161), 5):
    source = next(row for row in tasks if row[0] == selected_job)
    copies.append((
        selected_job, 99, source[2], source[3], source[4]
    ))

tasks.extend(copies)

conn.executemany(
    "INSERT INTO maintenance_tasks VALUES (?, ?, ?, ?, ?)", tasks
)
conn.commit()

# ==========================================================
# 6. DISPLAY TABLE COUNTS, COLUMNS AND FOREIGN KEYS
# ==========================================================
expected_counts = {
    "stations": 12,
    "bicycles": 80,
    "batteries": 100,
    "battery_assignments": 240,
    "journeys": 1520,
    "maintenance_jobs": 160,
    "maintenance_tasks": original_task_count + 5
}

print("TABLE COUNTS AND STRUCTURES")
for table, expected in expected_counts.items():
    count = conn.execute(
        f"SELECT COUNT(*) FROM {table}"
    ).fetchone()[0]
    assert count == expected

    print(f"\n{table}: {count:,} rows")
    for column in conn.execute(f"PRAGMA table_info({table})"):
        _, name, dtype, required, default, pk_position = column
        print(
            f"  {name}: {dtype}; NOT NULL={bool(required)}; "
            f"PK position={pk_position}"
        )
    print(
        "  Foreign keys:",
        conn.execute(f"PRAGMA foreign_key_list({table})").fetchall()
    )

assert len(conn.execute(
    "PRAGMA table_info(journeys)"
).fetchall()) >= 7

print("\nMISSING VALUES")
for table, field, expected in [
    ("journeys", "battery_temperature_c", 76),
    ("maintenance_jobs", "job_notes", 16)
]:
    total = expected_counts[table]
    missing = conn.execute(
        f"SELECT COUNT(*) FROM {table} WHERE {field} IS NULL"
    ).fetchone()[0]
    assert missing == expected
    print(f"{table}.{field}: {missing}/{total} = {missing / total:.2%}")

groups, duplicate_count = conn.execute("""
    SELECT COUNT(*), COALESCE(SUM(n - 1), 0)
    FROM (
        SELECT COUNT(*) AS n
        FROM maintenance_tasks
        GROUP BY job_id, task_description, labour_minutes, repair_cost
        HAVING COUNT(*) > 1
    )
""").fetchone()

assert groups == 5 and duplicate_count == 5

print("\nDUPLICATE TASK ENTRIES")
print("Original task records:", original_task_count)
print("Duplicate groups:", groups)
print("Additional copies:", duplicate_count)
print(
    "Copies as percentage of final task rows:",
    f"{duplicate_count / len(tasks):.2%}"
)

# ==========================================================
# 7. VALIDATE TIME, LOCATION AND BATTERY CONSISTENCY
# ==========================================================
checks = {
    "Overlapping journeys": """
        SELECT COUNT(*)
        FROM journeys a JOIN journeys b
          ON a.bicycle_id = b.bicycle_id
         AND a.journey_id < b.journey_id
        WHERE a.departure_at < b.arrival_at
          AND b.departure_at < a.arrival_at
    """,

    "Journeys during maintenance": """
        SELECT COUNT(*)
        FROM journeys j JOIN maintenance_jobs m
          ON j.bicycle_id = m.bicycle_id
        WHERE j.departure_at < COALESCE(m.completed_at, '9999-12-31')
          AND m.opened_at < j.arrival_at
    """,

    "Overlapping bicycle or battery assignments": """
        SELECT COUNT(*)
        FROM battery_assignments a JOIN battery_assignments b
          ON (a.bicycle_id = b.bicycle_id OR a.battery_id = b.battery_id)
         AND (
             a.bicycle_id < b.bicycle_id
             OR (a.bicycle_id = b.bicycle_id
                 AND a.installed_at < b.installed_at)
         )
        WHERE a.installed_at < b.removed_at
          AND b.installed_at < a.removed_at
    """,

    "Journeys outside assignment dates": """
        SELECT COUNT(*)
        FROM journeys j JOIN battery_assignments a
          ON j.bicycle_id = a.bicycle_id
         AND j.installed_at = a.installed_at
        WHERE j.departure_at < a.installed_at
           OR j.arrival_at > a.removed_at
    """,

    "Broken station continuity": """
        WITH ordered AS (
            SELECT *,
                LAG(end_station_id) OVER (
                    PARTITION BY bicycle_id ORDER BY departure_at
                ) AS previous_station
            FROM journeys
        )
        SELECT COUNT(*) FROM ordered
        WHERE previous_station IS NOT NULL
          AND start_station_id <> previous_station
    """,

    "Broken charge continuity": """
        WITH ordered AS (
            SELECT *,
                LAG(end_charge_pct) OVER (
                    PARTITION BY bicycle_id, installed_at
                    ORDER BY departure_at
                ) AS previous_charge
            FROM journeys
        )
        SELECT COUNT(*)
        FROM ordered j JOIN battery_assignments a
          ON j.bicycle_id = a.bicycle_id
         AND j.installed_at = a.installed_at
        WHERE ABS(j.start_charge_pct -
            COALESCE(j.previous_charge, a.initial_charge_pct)) > 0.001
    """,

    "Use before commissioning": """
        SELECT COUNT(*)
        FROM battery_assignments a
        JOIN bicycles b ON b.bicycle_id = a.bicycle_id
        JOIN batteries t ON t.battery_id = a.battery_id
        WHERE date(a.installed_at) < b.commissioned_on
           OR date(a.installed_at) < t.commissioned_on
    """,

    "Station capacity exceeded after recorded arrivals": """
        WITH movements AS (
            SELECT '2025-01-01 00:00:00' AS moment,
                   ((bicycle_id - 1) % 12) + 1 AS station_id,
                   1 AS change
            FROM bicycles
            UNION ALL
            SELECT departure_at, start_station_id, -1 FROM journeys
            UNION ALL
            SELECT arrival_at, end_station_id, 1 FROM journeys
        ),
        events AS (
            SELECT moment, station_id, SUM(change) AS change
            FROM movements GROUP BY moment, station_id
        ),
        occupancy AS (
            SELECT station_id,
                SUM(change) OVER (
                    PARTITION BY station_id ORDER BY moment
                    ROWS UNBOUNDED PRECEDING
                ) AS occupied
            FROM events
        )
        SELECT COUNT(*)
        FROM occupancy o JOIN stations s USING(station_id)
        WHERE occupied < 0 OR occupied > s.docking_capacity
    """
}

print("\nBUSINESS-RULE CHECKS")
for label, query in checks.items():
    violations = conn.execute(query).fetchone()[0]
    assert violations == 0, f"{label}: {violations} violations"
    print(f"{label}: passed")

assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
assert conn.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
assert conn.execute("PRAGMA foreign_key_check").fetchall() == []

# ==========================================================
# 8. TEST CONSTRAINT REJECTION WITHOUT KEEPING TEST RECORDS
# ==========================================================
def expect_rejection(label, sql, values):
    conn.execute("SAVEPOINT validation")
    rejected = False
    try:
        conn.execute(sql, values)
    except sqlite3.IntegrityError:
        rejected = True
    finally:
        conn.execute("ROLLBACK TO validation")
        conn.execute("RELEASE validation")
    assert rejected, f"Constraint did not reject: {label}"
    print("Passed:", label)

expect_rejection(
    "Composite battery-assignment primary key",
    "INSERT INTO battery_assignments VALUES (?, ?, ?, ?, ?)",
    assignments[0]
)

expect_rejection(
    "Composite maintenance-task primary key",
    "INSERT INTO maintenance_tasks VALUES (?, ?, ?, ?, ?)",
    tasks[0]
)

expect_rejection(
    "Foreign-key reference",
    "INSERT INTO maintenance_tasks VALUES (?, ?, ?, ?, ?)",
    (99999, 1, "Inspection", 10, 5)
)

expect_rejection(
    "Nonnegative repair cost",
    "INSERT INTO maintenance_tasks VALUES (?, ?, ?, ?, ?)",
    (1, 100, "Validation task", 10, -5)
)

expect_rejection(
    "Required station name",
    "INSERT INTO stations VALUES (?, ?, ?, ?)",
    (999, None, "Residential", 20)
)

expect_rejection(
    "Unique station name",
    "INSERT INTO stations VALUES (?, ?, ?, ?)",
    (999, stations[0][1], "Residential", 20)
)

conn.commit()
conn.close()

print("\nIntegrity check: ok")
print("Foreign-key check: no violations")
print("All validation checks passed.")
print(f"Database created: {db_path.resolve()}")
print(f"File size: {db_path.stat().st_size:,} bytes")

# ==========================================================
# 9. DOWNLOAD IN GOOGLE COLAB
# ==========================================================
try:
    from google.colab import files
except ImportError:
    print("Outside Colab: the database is saved in the working folder.")
else:
    files.download(str(db_path))