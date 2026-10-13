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

        pipeline = [
            {
                "$match": {
                    "date": {
                        "$gte": "2026-01-01",
                        "$lte": "2026-01-31",
                    },
                    "late_minutes": {"$gt": 0},
                }
            },
            {
                "$group": {
                    "_id": "$emp_code",
                    "total_late_minutes": {
                        "$sum": "$late_minutes"
                    },
                    "late_count": {"$sum": 1},
                }
            },
            {
                "$sort": {
                    "total_late_minutes": -1,
                    "_id": 1,
                }
            },
            {"$limit": 10},
        ]

        # Warm up the query.
        list(db.attendance_logs.aggregate(pipeline))

        start = time.perf_counter()

        results = list(
            db.attendance_logs.aggregate(pipeline)
        )

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

        print("========== LATE LEADERBOARD ==========")
        print("Database:", DB_NAME)
        print("Month: 2026-01")
        print("Leaderboard entries:", len(results))

        for rank, employee in enumerate(results, start=1):
            print(
                rank,
                employee["_id"],
                employee["total_late_minutes"],
                employee["late_count"],
            )

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

        print("\n========== VERIFICATION ==========")

        assert len(results) == 10
        assert stats["totalDocsExamined"] <= 31000

        print("PASS: Leaderboard returned 10 employees.")
        print("PASS: Query examined at most 31,000 documents.")

    finally:
        client.close()


if __name__ == "__main__":
    main()