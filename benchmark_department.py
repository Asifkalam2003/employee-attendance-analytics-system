import os
import time

from pymongo import MongoClient


DB_NAME = "hrone_attendance_performance"


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

        db = client[DB_NAME]

        employees = db.employees

        department = "Engineering"
        start_date = "2026-01-01"
        end_date = "2026-01-31"

        pipeline = [
            {
                "$match": {
                    "department": department,
                    "joined_on": {"$lte": end_date},
                }
            },
            {
                "$lookup": {
                    "from": "attendance_logs",
                    "let": {"code": "$emp_code"},
                    "pipeline": [
                        {
                            "$match": {
                                "date": {
                                    "$gte": start_date,
                                    "$lte": end_date,
                                },
                                "$expr": {
                                    "$eq": [
                                        "$emp_code",
                                        "$$code",
                                    ]
                                },
                            }
                        },
                        {
                            "$group": {
                                "_id": None,
                                "attendance_records": {
                                    "$sum": 1
                                },
                                "late_minutes": {
                                    "$sum": {
                                        "$ifNull": [
                                            "$late_minutes",
                                            0,
                                        ]
                                    }
                                },
                            }
                        },
                    ],
                    "as": "summary",
                }
            },
            {
                "$set": {
                    "summary": {
                        "$ifNull": [
                            {
                                "$arrayElemAt": [
                                    "$summary",
                                    0,
                                ]
                            },
                            {},
                        ]
                    }
                }
            },
            {
                "$group": {
                    "_id": "$department",
                    "headcount": {"$sum": 1},
                    "attendance_records": {
                        "$sum": {
                            "$ifNull": [
                                "$summary.attendance_records",
                                0,
                            ]
                        }
                    },
                    "total_late_minutes": {
                        "$sum": {
                            "$ifNull": [
                                "$summary.late_minutes",
                                0,
                            ]
                        }
                    },
                }
            },
        ]

        # Warm-up query.
        list(employees.aggregate(pipeline))

        # Measure aggregation time.
        start = time.perf_counter()

        result = list(employees.aggregate(pipeline))

        elapsed_ms = (
            time.perf_counter() - start
        ) * 1000

        # MongoDB execution plan.
        explain = db.command(
            "explain",
            {
                "aggregate": "employees",
                "pipeline": pipeline,
                "cursor": {},
            },
            verbosity="executionStats",
        )

        cursor_stage = next(
            stage["$cursor"]
            for stage in explain["stages"]
            if "$cursor" in stage
        )

        cursor_stats = cursor_stage["executionStats"]

        lookup_stage = next(
            stage
            for stage in explain["stages"]
            if "$lookup" in stage
        )

        print("========== DEPARTMENT SUMMARY ==========")
        print("Database:", DB_NAME)
        print("Department:", department)
        print("Month: 2026-01")
        print("Result:", result)

        print("\n========== PERFORMANCE ==========")
        print(f"Python query time: {elapsed_ms:.2f} ms")

        print(
            "Employee documents examined:",
            cursor_stats["totalDocsExamined"],
        )

        print(
            "Employee index keys examined:",
            cursor_stats["totalKeysExamined"],
        )

        print(
            "Attendance documents examined:",
            lookup_stage["totalDocsExamined"],
        )

        print(
            "Attendance index keys examined:",
            lookup_stage["totalKeysExamined"],
        )

        print(
            "Attendance lookup collection scans:",
            lookup_stage["collectionScans"],
        )

        print(
            "Attendance indexes used:",
            lookup_stage["indexesUsed"],
        )

        print("\n========== VERIFICATION ==========")

        assert len(result) == 1

        assert result[0]["headcount"] == 200

        assert result[0]["attendance_records"] == 6200

        assert lookup_stage["collectionScans"] == 0

        assert (
            "attendance_employee_date_unique"
            in lookup_stage["indexesUsed"]
        )

        print("PASS: Department headcount is 200.")
        print("PASS: Processed 6,200 attendance records.")
        print("PASS: Attendance lookup uses an index.")
        print("PASS: No attendance collection scan.")

    finally:
        client.close()


if __name__ == "__main__":
    main()