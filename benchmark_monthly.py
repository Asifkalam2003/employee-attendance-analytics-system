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
        attendance = db.attendance_logs

        employee_code = "PERF00001"

        start_date = "2026-01-01"
        end_date = "2026-01-31"

        pipeline = [
            {
                "$match": {
                    "emp_code": employee_code,
                    "date": {
                        "$gte": start_date,
                        "$lte": end_date,
                    },
                }
            },
            {
                "$group": {
                    "_id": "$emp_code",
                    "total_records": {"$sum": 1},
                    "present_days": {
                        "$sum": {
                            "$cond": [
                                {
                                    "$in": [
                                        "$status",
                                        ["PRESENT", "WFH", "ON_DUTY"],
                                    ]
                                },
                                1,
                                0,
                            ]
                        }
                    },
                    "total_late_minutes": {
                        "$sum": {
                            "$ifNull": ["$late_minutes", 0]
                        }
                    },
                    "total_overtime_minutes": {
                        "$sum": {
                            "$ifNull": ["$overtime_minutes", 0]
                        }
                    },
                }
            },
        ]

        # Warm up MongoDB.
        list(attendance.aggregate(pipeline))

        start = time.perf_counter()

        result = list(attendance.aggregate(pipeline))

        elapsed_ms = (
            time.perf_counter() - start
        ) * 1000

        explain = db.command(
            "explain",
            {
                "aggregate": "attendance_logs",
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

        stats = cursor_stage["executionStats"]

        print("========== MONTHLY ANALYTICS ==========")
        print("Database:", DB_NAME)
        print("Employee:", employee_code)
        print("Month: 2026-01")
        print("Result:", result)

        print("\n========== PERFORMANCE ==========")
        print(f"Python query time: {elapsed_ms:.2f} ms")
        print(
            "MongoDB cursor execution time:",
            stats["executionTimeMillis"],
            "ms",
        )
        print(
            "Index keys examined:",
            stats["totalKeysExamined"],
        )
        print(
            "Documents examined:",
            stats["totalDocsExamined"],
        )

        def find_stages(plan, stage_name):
            found = []

            if isinstance(plan, dict):
                if plan.get("stage") == stage_name:
                    found.append(plan)

                for value in plan.values():
                    found.extend(
                        find_stages(value, stage_name)
                    )

            elif isinstance(plan, list):
                for value in plan:
                    found.extend(
                        find_stages(value, stage_name)
                    )

            return found

        winning_plan = cursor_stage[
            "queryPlanner"
        ]["winningPlan"]

        index_scans = find_stages(
            winning_plan,
            "IXSCAN",
        )

        collection_scans = find_stages(
            winning_plan,
            "COLLSCAN",
        )

        print(
            "Indexes used:",
            [
                scan["indexName"]
                for scan in index_scans
            ],
        )

        print(
            "Collection scans:",
            len(collection_scans),
        )

        print("\n========== VERIFICATION ==========")

        assert len(result) == 1
        assert result[0]["total_records"] == 31
        assert index_scans
        assert not collection_scans
        assert stats["totalDocsExamined"] <= 31

        print("PASS: Monthly analytics returned 31 records.")
        print("PASS: MongoDB used an index.")
        print("PASS: No collection scan.")
        print("PASS: Examined at most 31 documents.")

    finally:
        client.close()


if __name__ == "__main__":
    main()