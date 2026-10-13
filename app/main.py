"""
Employee Attendance & Analytics API - STARTER

Run:  uvicorn app.main:app --port 8000
Env:  MONGO_URI, MONGO_DB (a local .env is loaded for convenience)

This file was written quickly by a colleague who has left the company. The happy path
works, but nobody has reviewed it. Read PROBLEM_STATEMENT.docx for what is expected of you,
openapi.yaml for the contract and DATA_MODEL.md for what is stored in MongoDB.
"""
import os
import calendar
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from typing import Annotated, Literal, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from pydantic import (
    BaseModel,
    BeforeValidator,
    Field,
    field_validator,
    model_validator,
)
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError, PyMongoError

from decimal import Decimal, ROUND_HALF_UP
from pymongo import ReturnDocument
import json
from bson import json_util

load_dotenv()

client = MongoClient(
    os.getenv("MONGO_URI", "mongodb://localhost:27017"),
    tz_aware=True,
    serverSelectionTimeoutMS=3000,
    connectTimeoutMS=3000,
)
db = client[os.getenv("MONGO_DB", "attendance_db")]

IST = timezone(timedelta(hours=5, minutes=30))

def validate_calendar_date(value):
    # API calendar dates must be strings in exact YYYY-MM-DD format.
    if not isinstance(value, str):
        raise ValueError("Date must use YYYY-MM-DD format")

    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        raise ValueError("Invalid calendar date")

    if parsed.isoformat() != value:
        raise ValueError("Date must use YYYY-MM-DD format")

    return parsed


CalendarDate = Annotated[
    date,
    BeforeValidator(validate_calendar_date),
]

@asynccontextmanager
async def lifespan(app: FastAPI):
    db.employees.create_index(
        [("emp_code", 1)],
        unique=True,
        name="employees_emp_code_unique",
    )
    db.attendance_logs.create_index(
        [("emp_code", 1), ("date", 1)],
        unique=True,
        name="attendance_employee_date_unique",
    )

    # Supports department filtering followed by employee-code ordering.
    db.employees.create_index(
        [("department", 1), ("emp_code", 1)],
        name="employees_department_emp_code",
    )

    # Supports chronological listing and date-range analytics.
    db.attendance_logs.create_index(
        [("date", -1), ("emp_code", 1)],
        name="attendance_date_emp_code",
    )

    # Supports status-filtered attendance listing.
    db.attendance_logs.create_index(
        [("status", 1), ("date", -1), ("emp_code", 1)],
        name="attendance_status_date_emp_code",
    )

        # Finds an employee's most recent qualifying punch-in.
    db.attendance_logs.create_index(
        [("emp_code", 1), ("punch_in", -1)],
        name="attendance_employee_punch_in",
    )

        # Supports eligibility filtering across all departments.
    db.employees.create_index(
        [("joined_on", 1), ("department", 1)],
        name="employees_joined_department",
    )

    # Supports eligibility filtering within one department.
    db.employees.create_index(
        [("department", 1), ("joined_on", 1)],
        name="employees_department_joined",
    )

    yield


app = FastAPI(
    title="Employee Attendance & Analytics API",
    version="2.0.0",
    lifespan=lifespan,
)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def compute_late_minutes(
    punch_in: datetime,
    shift_start: str,
    date_str: Optional[str] = None,
) -> int:
    # The explicit attendance date handles overnight shifts correctly.
    if date_str is None:
        date_str = punch_in.astimezone(IST).date().isoformat()

    start = shift_start_datetime(date_str, shift_start)
    seconds = int(
        (punch_in.replace(microsecond=0) - start).total_seconds()
    )

    # Check grace in seconds before flooring to whole minutes:
    # 10:00 late => 0; 10:01 late => 10 minutes.
    return seconds // 60 if seconds > 600 else 0


def compute_work_hours(punch_in: datetime, punch_out: datetime) -> float:
    seconds = int((punch_out - punch_in).total_seconds())

    # Decimal gives the half-up rounding required by the contract.
    hours = Decimal(seconds) / Decimal(3600)
    return float(hours.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def compute_overtime(
    punch_out: datetime,
    shift_end: str,
    date_str: str,
    shift_start: str,
) -> int:
    end = datetime.fromisoformat(
        f"{date_str}T{shift_end}:00"
    ).replace(tzinfo=IST)

    # Overnight shifts end on the day after the attendance date.
    if shift_end <= shift_start:
        end += timedelta(days=1)

    minutes = int((punch_out - end).total_seconds() // 60)

    # Overtime below 30 whole minutes does not count.
    return minutes if minutes >= 30 else 0

def epoch_to_datetime(value: int) -> datetime:
    # Discard milliseconds before storing or calculating an instant.
    return datetime.fromtimestamp(value // 1000, tz=timezone.utc)


def attendance_date(punch_in: datetime, employee: dict) -> str:
    local = punch_in.astimezone(IST)
    day = local.date()

    # Fixed-width HH:MM strings can be compared chronologically.
    overnight = employee["shift_end"] <= employee["shift_start"]

    # Early-morning punches belong to the previous overnight shift.
    if overnight and local.strftime("%H:%M") < employee["shift_end"]:
        day -= timedelta(days=1)

    return day.isoformat()


def shift_start_datetime(date_str: str, shift_start: str) -> datetime:
    # Anchor the shift to its attendance date, not the UTC punch date.
    return datetime.fromisoformat(
        f"{date_str}T{shift_start}:00"
    ).replace(tzinfo=IST)

def api_value(value):
    # Convert timestamps recursively, including dates inside audit history.
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
        return (value - epoch) // timedelta(milliseconds=1)

    if isinstance(value, dict):
        return {
            key: api_value(item)
            for key, item in value.items()
            if key != "_id"
        }

    if isinstance(value, list):
        return [api_value(item) for item in value]

    return value

def attendance_response(doc: dict) -> dict:
    # Older seeded records may omit these fields.
    result = dict(doc)
    result.setdefault("punch_in", None)
    result.setdefault("punch_out", None)
    result.setdefault("work_hours", None)
    result.setdefault("late_minutes", 0)
    result.setdefault("overtime_minutes", 0)
    result.setdefault("half_day", False)
    result.setdefault("history", [])
    return api_value(result)


def month_bounds(month: str):
    # Validate the calendar month and calculate its inclusive boundaries.
    try:
        year, month_number = map(int, month.split("-"))
        first = date(year, month_number, 1)
        last = date(
            year,
            month_number,
            calendar.monthrange(year, month_number)[1],
        )
    except (ValueError, OverflowError):
        raise HTTPException(422, "Invalid month")

    return first, last


def employee_monthly_pipeline(emp_code: str, month: str):
    first, last = month_bounds(month)

    # Calendar calculations use IST; stored log dates remain strings.
    first_dt = datetime(
        first.year, first.month, first.day, tzinfo=IST
    )
        # Keep the last day representable even for December 9999.
    last_dt = datetime(
        last.year, last.month, last.day, tzinfo=IST
    )

    presence = {"$in": ["$status", ["PRESENT", "WFH", "ON_DUTY"]]}
    weekday = {
        "$lte": [
            {
                "$isoDayOfWeek": {
                    "date": {"$dateFromString": {"dateString": "$date"}},
                    "timezone": "Asia/Kolkata",
                }
            },
            5,
        ]
    }

    return [
        # Starting from the employee preserves a result with zero logs.
        {"$match": {"emp_code": emp_code}},
        {
            "$lookup": {
                "from": "attendance_logs",
                "let": {"code": "$emp_code"},
                "pipeline": [
                    {
                        "$match": {
                            "date": {
                                "$gte": first.isoformat(),
                                "$lte": last.isoformat(),
                            },
                            "$expr": {"$eq": ["$emp_code", "$$code"]},
                        }
                    },
                    {
                        "$group": {
                            "_id": None,
                            "present_days": {
                                "$sum": {
                                    "$cond": [
                                        {"$and": [presence, weekday]},
                                        {
                                            "$cond": [
                                                {"$ifNull": ["$half_day", False]},
                                                0.5,
                                                1,
                                            ]
                                        },
                                        0,
                                    ]
                                }
                            },
                            "leave_days": {
                                "$sum": {
                                    "$cond": [
                                        {"$eq": ["$status", "LEAVE"]}, 1, 0
                                    ]
                                }
                            },
                            "late_count": {
                                "$sum": {
                                    "$cond": [
                                        {
                                            "$gt": [
                                                {"$ifNull": ["$late_minutes", 0]},
                                                0,
                                            ]
                                        },
                                        1,
                                        0,
                                    ]
                                }
                            },
                            "total_late_minutes": {
                                "$sum": {"$ifNull": ["$late_minutes", 0]}
                            },
                            "total_overtime_minutes": {
                                "$sum": {"$ifNull": ["$overtime_minutes", 0]}
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
                        {"$arrayElemAt": ["$summary", 0]},
                        {},
                    ]
                },
                # Mid-month joiners start at joined_on.
                "start_day": {
                    "$max": [
                        first_dt,
                        {
                            "$dateFromString": {
                                "dateString": "$joined_on",
                                "timezone": "Asia/Kolkata",
                            }
                        },
                    ]
                },
            }
        },
        {
            "$set": {
                # Generate calendar days inside MongoDB, not Python.
                "day_offsets": {
                    "$range": [
                        0,
                        {
                            "$toInt": {
                                "$max": [
                                    0,
                                    {
                                        "$dateDiff": {
                                            "startDate": "$start_day",
                                                                                        "endDate": {
                                                "$dateAdd": {
                                                    "startDate": last_dt,
                                                    "unit": "day",
                                                    "amount": 1,
                                                    "timezone": "Asia/Kolkata",
                                                }
                                            },
                                            "unit": "day",
                                            "timezone": "Asia/Kolkata",
                                        }
                                    },
                                ]
                            }
                        },
                    ]
                },
                "present_days": {
                    "$ifNull": ["$summary.present_days", 0]
                },
            }
        },
        {
            "$set": {
                "working_days": {
                    "$size": {
                        "$filter": {
                            "input": "$day_offsets",
                            "as": "offset",
                            "cond": {
                                "$lte": [
                                    {
                                        "$isoDayOfWeek": {
                                            "date": {
                                                "$dateAdd": {
                                                    "startDate": "$start_day",
                                                    "unit": "day",
                                                    "amount": "$$offset",
                                                    "timezone": "Asia/Kolkata",
                                                }
                                            },
                                            "timezone": "Asia/Kolkata",
                                        }
                                    },
                                    5,
                                ]
                            },
                        }
                    }
                }
            }
        },
        {
            "$project": {
                "_id": 0,
                "emp_code": 1,
                "month": {"$literal": month},
                "working_days": 1,
                "present_days": 1,
                "leave_days": {
                    "$ifNull": ["$summary.leave_days", 0]
                },
                "late_count": {
                    "$ifNull": ["$summary.late_count", 0]
                },
                "total_late_minutes": {
                    "$ifNull": ["$summary.total_late_minutes", 0]
                },
                "total_overtime_minutes": {
                    "$ifNull": ["$summary.total_overtime_minutes", 0]
                },
                "attendance_pct": {
                    "$cond": [
                        {"$gt": ["$working_days", 0]},
                        # For nonnegative numbers, floor(x + 0.5)
                        # implements half-up rounding. Use decimal arithmetic.
                        {
                            "$toDouble": {
                                "$divide": [
                                    {
                                        "$floor": {
                                            "$add": [
                                                {
                                                    "$divide": [
                                                        {
                                                            "$multiply": [
                                                                {
                                                                    "$toDecimal":
                                                                        "$present_days"
                                                                },
                                                                10000,
                                                            ]
                                                        },
                                                        "$working_days",
                                                    ]
                                                },
                                                {"$toDecimal": "0.5"},
                                            ]
                                        }
                                    },
                                    100,
                                ]
                            }
                        },
                        None,
                    ]
                },
            }
        },
    ]


def mongo_half_up(expression, places=2):
    scale = 10 ** places

    # All values rounded here are nonnegative.
    # Decimal arithmetic avoids binary-float rounding at ties.
    return {
        "$toDouble": {
            "$divide": [
                {
                    "$floor": {
                        "$add": [
                            {
                                "$multiply": [
                                    {"$toDecimal": expression},
                                    scale,
                                ]
                            },
                            {"$toDecimal": "0.5"},
                        ]
                    }
                },
                scale,
            ]
        }
    }
    

def department_summary_pipeline(month: str, department=None):
    first, last = month_bounds(month)

    # Include eligible employees even when they have no attendance logs.
    employee_filter = {"joined_on": {"$lte": last.isoformat()}}
    if department is not None:
        employee_filter["department"] = department

    presence = {"$in": ["$status", ["PRESENT", "WFH", "ON_DUTY"]]}
    weekday = {
        "$lte": [
            {
                "$isoDayOfWeek": {
                    "date": {"$dateFromString": {"dateString": "$date"}},
                    "timezone": "Asia/Kolkata",
                }
            },
            5,
        ]
    }
    completed_presence = {
        "$and": [
            presence,
            {"$ne": [{"$ifNull": ["$work_hours", None]}, None]},
        ]
    }

    return [
        {"$match": employee_filter},
        {
            "$lookup": {
                "from": "attendance_logs",
                "let": {"code": "$emp_code"},
                "pipeline": [
                    {
                        "$match": {
                            "date": {
                                "$gte": first.isoformat(),
                                "$lte": last.isoformat(),
                            },
                            "$expr": {"$eq": ["$emp_code", "$$code"]},
                        }
                    },
                    {
                        "$group": {
                            "_id": None,
                            "present_days": {
                                "$sum": {
                                    "$cond": [
                                        {"$and": [presence, weekday]},
                                        {
                                            "$cond": [
                                                {"$ifNull": ["$half_day", False]},
                                                0.5,
                                                1,
                                            ]
                                        },
                                        0,
                                    ]
                                }
                            },
                            # Carry sums and counts, not employee averages.
                            "work_sum": {
                                "$sum": {
                                    "$cond": [
                                        completed_presence,
                                        {"$toDecimal": "$work_hours"},
                                        0,
                                    ]
                                }
                            },
                            "work_count": {
                                "$sum": {
                                    "$cond": [completed_presence, 1, 0]
                                }
                            },
                            "late_count": {
                                "$sum": {
                                    "$cond": [
                                        {
                                            "$gt": [
                                                {"$ifNull": ["$late_minutes", 0]},
                                                0,
                                            ]
                                        },
                                        1,
                                        0,
                                    ]
                                }
                            },
                            "total_late_minutes": {
                                "$sum": {"$ifNull": ["$late_minutes", 0]}
                            },
                            "leave_count": {
                                "$sum": {
                                    "$cond": [
                                        {"$eq": ["$status", "LEAVE"]}, 1, 0
                                    ]
                                }
                            },
                            "on_duty_count": {
                                "$sum": {
                                    "$cond": [
                                        {"$eq": ["$status", "ON_DUTY"]}, 1, 0
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
                        {"$arrayElemAt": ["$summary", 0]},
                        {},
                    ]
                }
            }
        },
        {
            "$group": {
                "_id": "$department",
                "headcount": {"$sum": 1},
                "present_days": {
                    "$sum": {"$ifNull": ["$summary.present_days", 0]}
                },
                "work_sum": {
                    "$sum": {"$ifNull": ["$summary.work_sum", 0]}
                },
                "work_count": {
                    "$sum": {"$ifNull": ["$summary.work_count", 0]}
                },
                "late_count": {
                    "$sum": {"$ifNull": ["$summary.late_count", 0]}
                },
                "total_late_minutes": {
                    "$sum": {"$ifNull": ["$summary.total_late_minutes", 0]}
                },
                "leave_count": {
                    "$sum": {"$ifNull": ["$summary.leave_count", 0]}
                },
                "on_duty_count": {
                    "$sum": {"$ifNull": ["$summary.on_duty_count", 0]}
                },
            }
        },
        {
            "$project": {
                "_id": 0,
                "department": "$_id",
                "headcount": 1,
                "present_days": 1,
                "late_count": 1,
                "total_late_minutes": 1,
                "leave_count": 1,
                "on_duty_count": 1,
                "avg_work_hours": {
                    "$cond": [
                        {"$gt": ["$work_count", 0]},
                        mongo_half_up({
                            "$divide": ["$work_sum", "$work_count"]
                        }),
                        None,
                    ]
                },
            }
        },
        {"$sort": {"department": 1}},
    ]

def late_leaderboard_pipeline(month: str, limit: int, department=None):
    first, last = month_bounds(month)

    pipeline = [
        # Read only the requested month's records.
        {
            "$match": {
                "date": {
                    "$gte": first.isoformat(),
                    "$lte": last.isoformat(),
                }
            }
        },
        {
            "$group": {
                "_id": "$emp_code",
                "total_late_minutes": {
                    "$sum": {"$ifNull": ["$late_minutes", 0]}
                },
                "late_count": {
                    "$sum": {
                        "$cond": [
                            {
                                "$gt": [
                                    {"$ifNull": ["$late_minutes", 0]},
                                    0,
                                ]
                            },
                            1,
                            0,
                        ]
                    }
                },
            }
        },
        {"$match": {"total_late_minutes": {"$gt": 0}}},
        {
            "$lookup": {
                "from": "employees",
                "localField": "_id",
                "foreignField": "emp_code",
                "as": "employee",
            }
        },
        # Discard logs whose employee does not exist.
        {"$unwind": "$employee"},
    ]

    # Filter before ranking so ranks are within this department.
    if department is not None:
        pipeline.append({
            "$match": {"employee.department": department}
        })

    pipeline.extend([
        {
            "$setWindowFields": {
                # Rank by late minutes alone so ties share a rank.
                "sortBy": {"total_late_minutes": -1},
                "output": {"rank": {"$rank": {}}},
            }
        },
        # Apply the cutoff to ranks, preserving all qualifying ties.
        {"$match": {"rank": {"$lte": limit}}},
        {
            "$project": {
                "_id": 0,
                "emp_code": "$_id",
                "name": "$employee.name",
                "department": "$employee.department",
                "total_late_minutes": 1,
                "late_count": 1,
                "rank": 1,
            }
        },
        # Employee code makes the display order deterministic for ties.
        {"$sort": {"total_late_minutes": -1, "emp_code": 1}},
    ])

    return pipeline

def department_trend_pipeline(
    department: str,
    date_from: date,
    date_to: date,
):
    days = (date_to - date_from).days + 1
    if days < 1 or days > 92:
        raise HTTPException(
            422, "Date range must contain between 1 and 92 days"
        )

    start = datetime(
        date_from.year,
        date_from.month,
        date_from.day,
        tzinfo=IST,
    )

    return [
        # Include all department employees, even future joiners.
        # Their eligibility is checked separately for each day.
        {"$match": {"department": department}},
        {
            "$project": {
                "_id": 0,
                "emp_code": 1,
                "joined_on": 1,
                # Generate calendar days in MongoDB, not a Python loop.
                "day": {
                    "$map": {
                        "input": {"$range": [0, days]},
                        "as": "offset",
                        "in": {
                            "$dateAdd": {
                                "startDate": start,
                                "unit": "day",
                                "amount": "$$offset",
                                "timezone": "Asia/Kolkata",
                            }
                        },
                    }
                },
            }
        },
        {"$unwind": "$day"},
        {
            "$set": {
                "date": {
                    "$dateToString": {
                        "date": "$day",
                        "format": "%Y-%m-%d",
                        "timezone": "Asia/Kolkata",
                    }
                }
            }
        },
        {
            "$lookup": {
                "from": "attendance_logs",
                "let": {"code": "$emp_code", "date": "$date"},
                "pipeline": [
                    {
                        "$match": {
                            "$expr": {
                                "$and": [
                                    {"$eq": ["$emp_code", "$$code"]},
                                    {"$eq": ["$date", "$$date"]},
                                ]
                            }
                        }
                    },
                    {
                        "$project": {
                            "_id": 0,
                            "status": 1,
                            "half_day": 1,
                            "late_minutes": 1,
                        }
                    },
                ],
                "as": "logs",
            }
        },
        {
            "$set": {
                # An empty lookup still leaves the calendar row intact.
                "log": {
                    "$ifNull": [
                        {"$arrayElemAt": ["$logs", 0]},
                        {},
                    ]
                }
            }
        },
        {
            "$group": {
                "_id": "$day",
                "date": {"$first": "$date"},
                "headcount": {
                    "$sum": {
                        "$cond": [
                            {"$lte": ["$joined_on", "$date"]},
                            1,
                            0,
                        ]
                    }
                },
                # Trend presence includes weekend records.
                "present_count": {
                    "$sum": {
                        "$cond": [
                            {
                                "$in": [
                                    "$log.status",
                                    ["PRESENT", "WFH", "ON_DUTY"],
                                ]
                            },
                            {
                                "$cond": [
                                    {"$ifNull": ["$log.half_day", False]},
                                    0.5,
                                    1,
                                ]
                            },
                            0,
                        ]
                    }
                },
                "late_count": {
                    "$sum": {
                        "$cond": [
                            {
                                "$gt": [
                                    {"$ifNull": ["$log.late_minutes", 0]},
                                    0,
                                ]
                            },
                            1,
                            0,
                        ]
                    }
                },
            }
        },
        {
            "$set": {
                "is_working_day": {
                    "$lte": [
                        {
                            "$isoDayOfWeek": {
                                "date": "$_id",
                                "timezone": "Asia/Kolkata",
                            }
                        },
                        5,
                    ]
                }
            }
        },
        {
            "$set": {
                "attendance_rate": {
                    "$cond": [
                        {
                            "$and": [
                                "$is_working_day",
                                {"$gt": ["$headcount", 0]},
                            ]
                        },
                        mongo_half_up(
                            {
                                "$divide": [
                                    {"$toDecimal": "$present_count"},
                                    "$headcount",
                                ]
                            },
                            places=4,
                        ),
                        None,
                    ]
                }
            }
        },
        {
            "$setWindowFields": {
                "sortBy": {"_id": 1},
                "output": {
                    "moving_average": {
                        # Null weekend/zero-headcount rates are ignored.
                        "$avg": {"$toDecimal": "$attendance_rate"},
                        "window": {"documents": [-6, 0]},
                    }
                },
            }
        },
        {
            "$project": {
                "_id": 0,
                "date": 1,
                "is_working_day": 1,
                "headcount": 1,
                "present_count": 1,
                "late_count": 1,
                "attendance_rate": 1,
                "moving_avg_7d": {
                    "$cond": [
                        {"$ne": ["$moving_average", None]},
                        mongo_half_up("$moving_average", places=4),
                        None,
                    ]
                },
            }
        },
        {"$sort": {"date": 1}},
    ]

def attendance_query(emp_code, date_from, date_to, status):
    if date_from and date_to and date_from > date_to:
        raise HTTPException(
            422, "date_from must not be after date_to"
        )

    query = {}
    if emp_code is not None:
        query["emp_code"] = emp_code

    if date_from is not None or date_to is not None:
        query["date"] = {}
        if date_from is not None:
            query["date"]["$gte"] = date_from.isoformat()
        if date_to is not None:
            query["date"]["$lte"] = date_to.isoformat()

    if status is not None:
        query["status"] = status

    return query




# --------------------------------------------------------------------------- #
# Models
# --------------------------------------------------------------------------- #
class EmployeeIn(BaseModel):
    # Employee codes must contain EMP followed by 4–6 digits.
    emp_code: str = Field(pattern=r"^EMP[0-9]{4,6}$")

    name: str = Field(min_length=1, max_length=100)

    # Use the email pattern specified in the assignment's API contract.
    email: str = Field(
        max_length=120,
        pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
    )

    department: str = Field(min_length=1, max_length=50)

    # Shift times are IST clock values in 24-hour HH:MM format.
    shift_start: str = Field(
        default="09:30",
        pattern=r"^([01][0-9]|2[0-3]):[0-5][0-9]$",
    )
    shift_end: str = Field(
        default="18:30",
        pattern=r"^([01][0-9]|2[0-3]):[0-5][0-9]$",
    )

    # Keep calendar dates as strings to match MongoDB's data model.
    joined_on: str = Field(
        pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$",
    )

    @field_validator("joined_on")
    @classmethod
    def validate_joined_on(cls, value: str) -> str:
        # The pattern checks format; this rejects impossible calendar dates.
        # Pydantic converts a ValueError into a 422 validation response.
        date.fromisoformat(value)
        return value

    @model_validator(mode="after")
    def validate_shift(self):
        # Earlier end times are valid overnight shifts, but equal times
        # are explicitly forbidden by the employee creation contract.
        if self.shift_start == self.shift_end:
            raise ValueError("shift_start must differ from shift_end")
        return self

# Accept only integer epoch milliseconds within the contract's range.
# strict=True rejects strings, floats and booleans instead of converting them.
EpochMillis = Annotated[
    int,
    Field(
        strict=True,
        ge=100000000000,
        le=4102444800000,
    ),
]
class PunchInIn(BaseModel):
    emp_code: str

    # Omission means use the server clock; explicit null is invalid.
    punched_at: EpochMillis = Field(default_factory=lambda: (
        int(datetime.now(timezone.utc).timestamp()) * 1000
    ))

    # Only presence statuses can create a punch-in record.
    status: Literal["PRESENT", "WFH", "ON_DUTY"] = "PRESENT"

class PunchOutIn(BaseModel):
    emp_code: str
    punched_at: EpochMillis = Field(default_factory=lambda: (
        int(datetime.now(timezone.utc).timestamp()) * 1000
    ))

class RegularizeIn(BaseModel):
    status: Optional[
        Literal["PRESENT", "ABSENT", "LEAVE", "WFH", "ON_DUTY"]
    ] = None
    punch_in: Optional[EpochMillis] = None
    punch_out: Optional[EpochMillis] = None
    reason: str = Field(min_length=5, max_length=200)
    regularized_by: str = Field(min_length=1, max_length=50)

    @model_validator(mode="before")
    @classmethod
    def reject_explicit_nulls(cls, values):
        # Fields may be omitted, but the contract does not accept
        # explicit null values for these correction inputs.
        if isinstance(values, dict):
            for field in ("status", "punch_in", "punch_out"):
                if field in values and values[field] is None:
                    raise ValueError(f"{field} must not be null")
        return values


# --------------------------------------------------------------------------- #
# Endpoints provided
# --------------------------------------------------------------------------- #
@app.get("/health")
def health():
    try:
        client.admin.command("ping")
    except PyMongoError:
        raise HTTPException(
            status_code=503,
            detail="MongoDB is unavailable",
        )
    return {"status": "ok"}


@app.post("/employees", status_code=201)
def create_employee(body: EmployeeIn):
    doc = body.model_dump()

    # Store an aware UTC datetime, truncated to whole seconds.
    created_at = datetime.now(timezone.utc).replace(microsecond=0)
    doc["created_at"] = created_at

    try:
        # The unique index handles duplicates safely, even when
        # two requests insert the same employee code concurrently.
        db.employees.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(
            status_code=409,
            detail="emp_code already exists",
        )

    # MongoDB adds _id during insertion; it is internal to the database.
    doc.pop("_id", None)

    # The HTTP contract requires integer epoch milliseconds.
    doc["created_at"] = int(created_at.timestamp()) * 1000
    return doc


@app.get("/employees")
def list_employees(
    department: Optional[str] = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    # Use the same filter for both the results and their total.
    query = {}
    if department is not None:
        query["department"] = department

    # Page 1 starts at the first document.
    skip = (page - 1) * page_size
    total = db.employees.count_documents(query)

    # MongoDB sorts and paginates before we load this page into memory.
    cursor = (
        db.employees.find(query, {"_id": 0})
        .sort("emp_code", 1)
        .skip(skip)
        .limit(page_size)
    )

    items = []
    for doc in cursor:
        # BSON timestamps become epoch milliseconds at the API boundary.
        created_at = doc["created_at"]
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        doc["created_at"] = int(created_at.timestamp() * 1000)
        items.append(doc)

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@app.post("/attendance/punch-in", status_code=201)
def punch_in(body: PunchInIn):
    employee = db.employees.find_one({"emp_code": body.emp_code})

    # Check employee existence before accessing their shift details.
    if employee is None:
        raise HTTPException(
            status_code=404,
            detail="Employee not found",
        )

    # Convert milliseconds to UTC and truncate to whole seconds.
    timestamp = epoch_to_datetime(body.punched_at)
    day = attendance_date(timestamp, employee)

    doc = {
        "emp_code": body.emp_code,
        "date": day,
        "status": body.status,
        "punch_in": timestamp,
        "punch_out": None,
        "work_hours": None,
        "late_minutes": compute_late_minutes(
            timestamp,
            employee["shift_start"],
            day,
        ),
        "overtime_minutes": 0,
        "half_day": False,
        # Original punch events do not create correction history.
        "history": [],
    }

    try:
        # The unique employee/date index decides concurrent duplicates.
        db.attendance_logs.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(
            status_code=409,
            detail="Already punched in for this date",
        )

    # Return epoch milliseconds and omit MongoDB's internal _id.
    return api_value(doc)

@app.post("/attendance/punch-out")
def punch_out(body: PunchOutIn):
    employee = db.employees.find_one({"emp_code": body.emp_code})
    if employee is None:
        raise HTTPException(404, "Employee not found")

    timestamp = epoch_to_datetime(body.punched_at)

    # Find the latest qualifying punch-in, including closed records.
    # Searching only open records could incorrectly close an older shift.
    record = db.attendance_logs.find_one(
        {
            "emp_code": body.emp_code,
            "punch_in": {"$type": "date", "$lte": timestamp},
        },
        sort=[("punch_in", -1)],
    )

    if record is None:
        raise HTTPException(404, "No punch-in found")

    if record.get("punch_out") is not None:
        raise HTTPException(409, "Already punched out")

    duration = timestamp - record["punch_in"]
    if duration <= timedelta(0) or duration > timedelta(hours=24):
        raise HTTPException(
            422,
            "Punch-out must be after punch-in and within 24 hours",
        )

    hours = compute_work_hours(record["punch_in"], timestamp)
    overtime = compute_overtime(
        timestamp,
        employee["shift_end"],
        record["date"],
        employee["shift_start"],
    )

    # Compare the original record before updating. Only one concurrent
    # punch-out succeeds; corrections made meanwhile cause a conflict.
    updated = db.attendance_logs.find_one_and_update(
        record,
        {
            "$set": {
                "punch_out": timestamp,
                "work_hours": hours,
                "overtime_minutes": overtime,
                "half_day": hours < 4.50,
            }
        },
        return_document=ReturnDocument.AFTER,
    )

    if updated is None:
        raise HTTPException(409, "Attendance record changed; retry")

    # Punch-out leaves correction history unchanged.
    return attendance_response(updated)


@app.patch("/attendance/{emp_code}/{date}")
def regularize_attendance(
    emp_code: str,
    date: CalendarDate,
    body: RegularizeIn,
):
    day = date.isoformat()
    employee = db.employees.find_one({"emp_code": emp_code})
    if employee is None:
        raise HTTPException(404, "Employee not found")

    record = db.attendance_logs.find_one({
        "emp_code": emp_code,
        "date": day,
    })
    if record is None:
        raise HTTPException(404, "Attendance record not found")

    # Omitted fields keep their stored values.
    supplied = body.model_fields_set
    status = body.status if "status" in supplied else record["status"]
    punch_in_time = record.get("punch_in")
    punch_out_time = record.get("punch_out")

    if status in ("ABSENT", "LEAVE"):
        # Non-presence statuses clear times automatically.
        if "punch_in" in supplied or "punch_out" in supplied:
            raise HTTPException(
                422, "ABSENT or LEAVE cannot include punch times"
            )
        punch_in_time = None
        punch_out_time = None
    else:
        if "punch_in" in supplied:
            punch_in_time = epoch_to_datetime(body.punch_in)
        if "punch_out" in supplied:
            punch_out_time = epoch_to_datetime(body.punch_out)

        if punch_in_time is None:
            raise HTTPException(422, "Presence requires punch_in")

        punch_in_time = punch_in_time.replace(microsecond=0)
        if attendance_date(punch_in_time, employee) != day:
            raise HTTPException(
                422, "Punch-in must stay on the attendance date"
            )

        if punch_out_time is not None:
            punch_out_time = punch_out_time.replace(microsecond=0)
            duration = punch_out_time - punch_in_time
            if duration <= timedelta(0) or duration > timedelta(hours=24):
                raise HTTPException(
                    422, "Punch-out must be after punch-in and within 24 hours"
                )

    # Recompute every derived field from the final status and times.
    final = {
        "status": status,
        "punch_in": punch_in_time,
        "punch_out": punch_out_time,
        "work_hours": None,
        "late_minutes": 0,
        "overtime_minutes": 0,
        "half_day": False,
    }

    if punch_in_time is not None:
        final["late_minutes"] = compute_late_minutes(
            punch_in_time, employee["shift_start"], day
        )
        if punch_out_time is not None:
            hours = compute_work_hours(punch_in_time, punch_out_time)
            final["work_hours"] = hours
            final["overtime_minutes"] = compute_overtime(
                punch_out_time,
                employee["shift_end"],
                day,
                employee["shift_start"],
            )
            final["half_day"] = hours < 4.50

    defaults = {
        "punch_in": None,
        "punch_out": None,
        "work_hours": None,
        "late_minutes": 0,
        "overtime_minutes": 0,
        "half_day": False,
    }

    # Audit only fields whose values actually changed.
    changes = {}
    for field, value in final.items():
        previous = record.get(field, defaults.get(field))
        if previous != value:
            changes[field] = {"from": previous, "to": value}

    if not changes:
        raise HTTPException(422, "Correction changes nothing")

    entry = {
        "at": datetime.now(timezone.utc).replace(microsecond=0),
        "by": body.regularized_by,
        "reason": body.reason,
        "changes": changes,
    }

    # Match the original snapshot so a concurrent edit cannot silently
    # overwrite changes or append history based on outdated values.
    condition = dict(record)
    for field in (*final.keys(), "history"):
        if field not in record:
            condition[field] = {"$exists": False}

    updated = db.attendance_logs.find_one_and_update(
        condition,
        {
            "$set": final,
            "$push": {"history": entry},
        },
        return_document=ReturnDocument.AFTER,
    )

    if updated is None:
        raise HTTPException(409, "Attendance record changed; retry")

    return attendance_response(updated)



@app.get("/attendance")
def list_attendance(
    emp_code: Optional[str] = None,
    date_from: Optional[CalendarDate] = None,
    date_to: Optional[CalendarDate] = None,
    status: Optional[
        Literal["PRESENT", "ABSENT", "LEAVE", "WFH", "ON_DUTY"]
    ] = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    # Share filter construction and date-range validation with explain.
    query = attendance_query(
        emp_code, date_from, date_to, status
    )

    # Count all matching records, independently of pagination.
    total = db.attendance_logs.count_documents(query)

    # MongoDB sorts and paginates before we load the requested page.
    cursor = (
        db.attendance_logs.find(query, {"_id": 0})
        .sort([("date", -1), ("emp_code", 1)])
        .skip((page - 1) * page_size)
        .limit(page_size)
    )

    return {
        "items": [attendance_response(doc) for doc in cursor],
        "total": total,
        "page": page,
        "page_size": page_size,
    }

@app.get("/analytics/employees/{emp_code}/monthly")
def employee_monthly(
    emp_code: str,
    month: str = Query(
        ...,
        pattern=r"^[0-9]{4}-(0[1-9]|1[0-2])$",
    ),
):
    # Reuse this builder later for the explain endpoint.
    pipeline = employee_monthly_pipeline(emp_code, month)
    results = list(db.employees.aggregate(pipeline))

    if not results:
        raise HTTPException(404, "Employee not found")
    return results[0]

@app.get("/analytics/departments/summary")
def department_summary(
    month: str = Query(
        ...,
        pattern=r"^[0-9]{4}-(0[1-9]|1[0-2])$",
    ),
    department: Optional[str] = None,
):
    pipeline = department_summary_pipeline(month, department)
    return {
        "month": month,
        "items": list(db.employees.aggregate(pipeline)),
    }

@app.get("/analytics/leaderboard/late")
def late_leaderboard(
    month: str = Query(
        ...,
        pattern=r"^[0-9]{4}-(0[1-9]|1[0-2])$",
    ),
    limit: int = Query(default=10, ge=1, le=50),
    department: Optional[str] = None,
):
    pipeline = late_leaderboard_pipeline(month, limit, department)
    return {
        "month": month,
        "items": list(db.attendance_logs.aggregate(pipeline)),
    }


@app.get("/analytics/departments/{department}/trend")
def department_trend(
    department: str,
    date_from: CalendarDate = Query(..., alias="from"),
    date_to: CalendarDate = Query(..., alias="to"),
):
    pipeline = department_trend_pipeline(
        department, date_from, date_to
    )

    if db.employees.find_one({"department": department}) is None:
        raise HTTPException(404, "Department not found")

    return {
        "department": department,
        "items": list(db.employees.aggregate(pipeline)),
    }

@app.get("/admin/explain/{endpoint}")
def explain_endpoint(
    endpoint: Literal[
        "attendance_list",
        "employee_monthly",
        "department_summary",
        "late_leaderboard",
        "department_trend",
    ],
    emp_code: Optional[str] = None,
    month: Optional[str] = Query(
        default=None,
        pattern=r"^[0-9]{4}-(0[1-9]|1[0-2])$",
    ),
    department: Optional[str] = None,
    limit: int = Query(default=10, ge=1, le=50),
    date_from: Optional[CalendarDate] = None,
    date_to: Optional[CalendarDate] = None,
    status: Optional[
        Literal["PRESENT", "ABSENT", "LEAVE", "WFH", "ON_DUTY"]
    ] = None,
    from_date: Optional[CalendarDate] = Query(default=None, alias="from"),
    to_date: Optional[CalendarDate] = Query(default=None, alias="to"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    if endpoint == "attendance_list":
        collection = "attendance_logs"

        # Match the real list query's projection, sort and pagination.
        command = {
            "find": collection,
            "filter": attendance_query(
                emp_code, date_from, date_to, status
            ),
            "projection": {"_id": 0},
            "sort": {"date": -1, "emp_code": 1},
            "skip": (page - 1) * page_size,
            "limit": page_size,
        }

    else:
        if endpoint == "department_trend":
            if (
                department is None
                or from_date is None
                or to_date is None
            ):
                raise HTTPException(
                    422, "department, from and to are required"
                )

            collection = "employees"
            pipeline = department_trend_pipeline(
                department, from_date, to_date
            )

        else:
            if month is None:
                raise HTTPException(422, "month is required")

            if endpoint == "employee_monthly":
                if emp_code is None:
                    raise HTTPException(422, "emp_code is required")

                collection = "employees"
                pipeline = employee_monthly_pipeline(emp_code, month)

            elif endpoint == "department_summary":
                collection = "employees"
                pipeline = department_summary_pipeline(
                    month, department
                )

            else:
                collection = "attendance_logs"
                pipeline = late_leaderboard_pipeline(
                    month, limit, department
                )

        command = {
            "aggregate": collection,
            "pipeline": pipeline,
            "cursor": {},
        }

    # Explain executes the query and returns its execution statistics.
    result = db.command({
        "explain": command,
        "verbosity": "executionStats",
    })

    # Preserve the complete explain document, including internal fields.
    # Extended JSON handles BSON values that ordinary JSON cannot encode.
    return {
        "endpoint": endpoint,
        "collection": collection,
        "explain": json.loads(json_util.dumps(result)),
    }


