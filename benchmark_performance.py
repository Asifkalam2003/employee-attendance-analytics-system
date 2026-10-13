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

        total = attendance.count_documents({})

        print("========== DATABASE ==========")
        print("Database:", DB_NAME)
        print("Attendance records:", total)

        if total != 100000:
            print("STOP: Expected exactly 100,000 records.")
            return

        # Query one employee's attendance records.
        query = {
            "emp_code": "PERF00001"
        }

        # Warm up MongoDB.
        list(
            attendance.find(query)
            .sort("date", -1)
            .limit(20)
        )

        # Measure query execution.
        start = time.perf_counter()

        records = list(
            attendance.find(query)
            .sort("date", -1)
            .limit(20)
        )

        elapsed_ms = (
            time.perf_counter() - start
        ) * 1000

        # Inspect MongoDB's execution plan.
        explain = db.command(
            "explain",
            {
                "find": "attendance_logs",
                "filter": query,
                "sort": {"date": -1},
                "limit": 20,
            },
            verbosity="executionStats",
        )

        stats = explain["executionStats"]

        print("\n========== QUERY PERFORMANCE ==========")
        print("Employee:", query["emp_code"])
        print("Records returned:", len(records))
        print(f"Python query time: {elapsed_ms:.2f} ms")

        print("\n========== MONGODB EXECUTION ==========")
        print(
            "MongoDB execution time:",
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

        winning_plan = explain["queryPlanner"]["winningPlan"]

        def inspect_plan(plan):
            if isinstance(plan, dict):
                if plan.get("stage") == "IXSCAN":
                    print(
                        "Index used:",
                        plan.get("indexName"),
                    )

                if plan.get("stage") == "COLLSCAN":
                    print("WARNING: Collection scan detected!")

                for value in plan.values():
                    inspect_plan(value)

            elif isinstance(plan, list):
                for item in plan:
                    inspect_plan(item)

        inspect_plan(winning_plan)

        print("\n========== VERIFICATION ==========")

        assert len(records) == 20
        assert stats["totalDocsExamined"] <= 20

        print("PASS: Query returned 20 records.")
        print("PASS: Query examined at most 20 documents.")

    finally:
        client.close()


if __name__ == "__main__":
    main()