import os
import random
import time
from datetime import date, timedelta

from pymongo import MongoClient, ASCENDING, DESCENDING


PERFORMANCE_DB = "hrone_attendance_performance"

EMPLOYEE_COUNT = 1000
DAYS_PER_EMPLOYEE = 100

DEPARTMENTS = [
    "Engineering",
    "Sales",
    "HR",
    "Finance",
    "Marketing",
]


def main():
    mongo_uri = os.getenv(
        "MONGODB_URI",
        "mongodb://localhost:27017"
    )

    client = MongoClient(
        mongo_uri,
        serverSelectionTimeoutMS=5000
    )

    try:
        client.admin.command("ping")

        db = client[PERFORMANCE_DB]

        employees = db.employees
        attendance = db.attendance_logs

        # Safety check: never overwrite existing data.
        existing_employees = employees.count_documents({})
        existing_attendance = attendance.count_documents({})

        if existing_employees or existing_attendance:
            print("STOP: Performance database already contains data.")
            print("Employees:", existing_employees)
            print("Attendance records:", existing_attendance)
            return

        print("Connected to MongoDB.")
        print("Database:", db.name)

        # Create indexes.
        employees.create_index(
            [("emp_code", ASCENDING)],
            unique=True,
            name="employees_emp_code_unique",
        )

        employees.create_index(
            [("department", ASCENDING), ("joined_on", ASCENDING)],
            name="employees_department_joined",
        )

        employees.create_index(
            [("department", ASCENDING), ("emp_code", ASCENDING)],
            name="employees_department_emp_code",
        )

        attendance.create_index(
            [("emp_code", ASCENDING), ("date", ASCENDING)],
            unique=True,
            name="attendance_employee_date_unique",
        )

        attendance.create_index(
            [("date", DESCENDING), ("emp_code", ASCENDING)],
            name="attendance_date_emp_code",
        )

        print("Indexes created successfully.")

        # Create 1,000 employees.
        employee_docs = []

        for i in range(EMPLOYEE_COUNT):
            employee_docs.append({
                "emp_code": f"PERF{i + 1:05d}",
                "name": f"Performance Employee {i + 1}",
                "department": DEPARTMENTS[i % len(DEPARTMENTS)],
                "joined_on": "2025-01-01",
            })

        employees.insert_many(employee_docs)

        print(f"Inserted {EMPLOYEE_COUNT} employees.")

        # Generate 100,000 attendance records.
        random.seed(42)

        start_date = date(2026, 1, 1)
        batch = []
        total_inserted = 0

        start_time = time.perf_counter()

        for employee in employee_docs:
            for day_offset in range(DAYS_PER_EMPLOYEE):
                attendance_date = start_date + timedelta(
                    days=day_offset
                )

                status = random.choices(
                    ["PRESENT", "WFH", "ON_DUTY", "LEAVE", "ABSENT"],
                    weights=[70, 12, 5, 8, 5],
                )[0]

                is_working = status in (
                    "PRESENT",
                    "WFH",
                    "ON_DUTY",
                )

                work_hours = (
                    round(random.uniform(4, 10), 2)
                    if is_working
                    else None
                )

                late_minutes = (
                    random.randint(0, 60)
                    if is_working
                    else 0
                )

                overtime_minutes = (
                    random.randint(0, 90)
                    if is_working
                    else 0
                )

                batch.append({
                    "emp_code": employee["emp_code"],
                    "date": attendance_date.isoformat(),
                    "status": status,
                    "work_hours": work_hours,
                    "half_day": (
                        work_hours < 4.5
                        if work_hours is not None
                        else False
                    ),
                    "late_minutes": late_minutes,
                    "overtime_minutes": overtime_minutes,
                    "punch_in": None,
                    "punch_out": None,
                    "history": [],
                })

                # Insert records in batches.
                if len(batch) >= 5000:
                    attendance.insert_many(batch, ordered=False)

                    total_inserted += len(batch)
                    batch.clear()

                    print(
                        f"Inserted {total_inserted:,} "
                        "attendance records..."
                    )

        if batch:
            attendance.insert_many(batch, ordered=False)
            total_inserted += len(batch)

        elapsed = time.perf_counter() - start_time

        print("\n========== RESULTS ==========")
        print("Employees:", employees.count_documents({}))
        print(
            "Attendance records:",
            attendance.count_documents({})
        )
        print(f"Insertion time: {elapsed:.2f} seconds")

        assert employees.count_documents({}) == EMPLOYEE_COUNT
        assert attendance.count_documents({}) == (
            EMPLOYEE_COUNT * DAYS_PER_EMPLOYEE
        )

        print("PASS: Exactly 100,000 attendance records created.")

    finally:
        client.close()


if __name__ == "__main__":
    main()