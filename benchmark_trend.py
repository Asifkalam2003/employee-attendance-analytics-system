import os
import time
from datetime import date, timedelta

from pymongo import MongoClient


DB_NAME = "hrone_attendance_performance"


def main():
    client = MongoClient(
        os.getenv("MONGODB_URI", "mongodb://localhost:27017"),
        serverSelectionTimeoutMS=5000,
    )

    try:
        client.admin.command("ping")
        db = client[DB_NAME]

        department = "Engineering"
        start_date = date(2026, 1, 1)
        end_date = date(2026, 1, 7)

        dates = [
            (start_date + timedelta(days=i)).isoformat()
            for i in range((end_date - start_date).days + 1)
        ]

        pipeline = [
            {
                "$match": {
                    "department": department,
                    "joined_on": {"$lte": end_date.isoformat()},
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
                                    "$gte": dates[0],
                                    "$lte": dates[-1],
                                },
                                "$expr": {
                                    "$eq": ["$emp_code", "$$code"]
                                },
                            }
                        },
                        {
                            "$group": {
                                "_id": "$date",
                                "present": {
                                    "$sum": {
                                        "$cond": [
                                            {
                                                "$in": [
                                                    "$status",
                                                    [
                                                        "PRESENT",
                                                        "WFH",
                                                        "ON_DUTY",
                                                    ],
                                                ]
                                            },
                                            1,
                                            0,
                                        ]
                                    }
                                },
                            }
                        },
                    ],
                    "as": "attendance",
                }
            },
            {"$unwind": "$attendance"},
            {
                "$group": {
                    "_id": "$attendance._id",
                    "present_count": {
                        "$sum": "$attendance.present"
                    },
                }
            },
            {"$sort": {"_id": 1}},
        ]

        # Warm up.
        list(db.employees.aggregate(pipeline))

        start = time.perf_counter()
        results = list(db.employees.aggregate(pipeline))
        elapsed_ms = (time.perf_counter() - start) * 1000

        explain = db.command(
            "explain",
            {
                "aggregate": "employees",
                "pipeline": pipeline,
                "cursor": {},
            },
            verbosity="executionStats",
        )

        lookup_stage = next(
            stage
            for stage in explain["stages"]
            if "$lookup" in stage
        )

        print("========== DEPARTMENT TREND ==========")
        print("Database:", DB_NAME)
        print("Department:", department)
        print("Date range:", dates[0], "to", dates[-1])

        for item in results:
            print(
                item["_id"],
                "Present employees:",
                item["present_count"],
            )

        print("\n========== PERFORMANCE ==========")
        print(f"Python query time: {elapsed_ms:.2f} ms")
        print(
            "Attendance documents examined:",
            lookup_stage["totalDocsExamined"],
        )
        print(
            "Attendance index keys examined:",
            lookup_stage["totalKeysExamined"],
        )
        print(
            "Collection scans:",
            lookup_stage["collectionScans"],
        )
        print(
            "Indexes used:",
            lookup_stage["indexesUsed"],
        )

        print("\n========== VERIFICATION ==========")

        assert len(results) == 7
        assert lookup_stage["collectionScans"] == 0
        assert (
            "attendance_employee_date_unique"
            in lookup_stage["indexesUsed"]
        )

        print("PASS: Seven daily trend records returned.")
        print("PASS: No attendance collection scan.")
        print("PASS: Attendance lookup uses an index.")

    finally:
        client.close()


if __name__ == "__main__":
    main()