import requests
import random
from datetime import datetime, timezone, timedelta

BASE_URL = "http://127.0.0.1:8000"

IST = timezone(timedelta(hours=5, minutes=30))


def to_millis(date_string, time_string):
    dt = datetime.fromisoformat(
        f"{date_string}T{time_string}"
    ).replace(tzinfo=IST)

    return int(dt.timestamp() * 1000)


def create_employee():
    emp_code = f"EMP{random.randint(100000, 999999)}"

    payload = {
        "emp_code": emp_code,
        "name": "Edge Case Tester",
        "email": f"{emp_code.lower()}@example.com",
        "department": "QA",
        "shift_start": "09:30",
        "shift_end": "18:30",
        "joined_on": "2026-01-01"
    }

    response = requests.post(
        f"{BASE_URL}/employees",
        json=payload,
        timeout=10
    )

    assert response.status_code == 201, (
        f"Employee creation failed: "
        f"{response.status_code} {response.text}"
    )

    return emp_code


def test_late_boundary():
    print("\nTesting Late Arrival Grace Period")
    print("-" * 45)

    tests = [
        ("2026-10-14", "09:40:00", 0),
        ("2026-10-15", "09:40:01", 10),
    ]

    for date_string, time_string, expected in tests:
        emp_code = create_employee()

        payload = {
            "emp_code": emp_code,
            "punched_at": to_millis(
                date_string,
                time_string
            ),
            "status": "PRESENT"
        }

        response = requests.post(
            f"{BASE_URL}/attendance/punch-in",
            json=payload,
            timeout=10
        )

        assert response.status_code == 201, (
            f"Punch-in failed: "
            f"{response.status_code} {response.text}"
        )

        actual = response.json()["late_minutes"]

        assert actual == expected, (
            f"Expected {expected}, got {actual}"
        )

        print(
            f"PASS: {time_string} IST "
            f"-> late_minutes={actual}"
        )

def test_overtime_boundary():
    print("\nTesting Overtime Threshold")
    print("-" * 45)

    tests = [
        ("2026-10-16", "18:59:00", 0),
        ("2026-10-19", "19:00:00", 30),
    ]

    for date_string, punch_out_time, expected in tests:
        emp_code = create_employee()

        punch_in_payload = {
            "emp_code": emp_code,
            "punched_at": to_millis(date_string, "09:30:00"),
            "status": "PRESENT",
        }

        punch_in_response = requests.post(
            f"{BASE_URL}/attendance/punch-in",
            json=punch_in_payload,
            timeout=10,
        )

        assert punch_in_response.status_code == 201, (
            f"Punch-in failed: {punch_in_response.text}"
        )

        punch_out_payload = {
            "emp_code": emp_code,
            "punched_at": to_millis(date_string, punch_out_time),
        }

        punch_out_response = requests.post(
            f"{BASE_URL}/attendance/punch-out",
            json=punch_out_payload,
            timeout=10,
        )

        assert punch_out_response.status_code == 200, (
            f"Punch-out failed: {punch_out_response.text}"
        )

        actual = punch_out_response.json()["overtime_minutes"]

        assert actual == expected, (
            f"Expected {expected}, got {actual}"
        )

        print(
            f"PASS: Punch-out at {punch_out_time} IST "
            f"-> overtime_minutes={actual}"
        )

def test_work_hours_and_half_day():
    print("\nTesting Work-Hours Rounding and Half-Day")
    print("-" * 45)

    tests = [
        # Date, punch-out time, expected hours, expected half-day
        ("2026-10-20", "13:59:24", 4.49, True),
        ("2026-10-21", "14:00:00", 4.50, False),
        ("2026-10-22", "14:00:18", 4.51, False),
    ]

    for date_string, punch_out_time, expected_hours, expected_half_day in tests:
        emp_code = create_employee()

        punch_in_response = requests.post(
            f"{BASE_URL}/attendance/punch-in",
            json={
                "emp_code": emp_code,
                "punched_at": to_millis(date_string, "09:30:00"),
                "status": "PRESENT",
            },
            timeout=10,
        )

        assert punch_in_response.status_code == 201, (
            f"Punch-in failed: "
            f"{punch_in_response.status_code} "
            f"{punch_in_response.text}"
        )

        punch_out_response = requests.post(
            f"{BASE_URL}/attendance/punch-out",
            json={
                "emp_code": emp_code,
                "punched_at": to_millis(date_string, punch_out_time),
            },
            timeout=10,
        )

        assert punch_out_response.status_code == 200, (
            f"Punch-out failed: "
            f"{punch_out_response.status_code} "
            f"{punch_out_response.text}"
        )

        data = punch_out_response.json()

        actual_hours = data["work_hours"]
        actual_half_day = data["half_day"]

        assert actual_hours == expected_hours, (
            f"Expected {expected_hours} hours, "
            f"got {actual_hours}"
        )

        assert actual_half_day is expected_half_day, (
            f"Expected half_day={expected_half_day}, "
            f"got {actual_half_day}"
        )

        print(
            f"PASS: {punch_out_time} IST "
            f"-> work_hours={actual_hours}, "
            f"half_day={actual_half_day}"
        )

def test_overnight_shift():
    print("\nTesting Overnight Shift")
    print("-" * 45)

    emp_code = create_employee()

    # This test needs an overnight shift.
    # Create a separate employee with the correct shift.
    import uuid

    emp_code = f"EMP{uuid.uuid4().int % 1000000:06d}"

    response = requests.post(
        f"{BASE_URL}/employees",
        json={
            "emp_code": emp_code,
            "name": "Overnight Shift Tester",
            "email": f"{emp_code.lower()}@example.com",
            "department": "QA",
            "shift_start": "22:00",
            "shift_end": "06:00",
            "joined_on": "2026-01-01",
        },
        timeout=10,
    )

    assert response.status_code == 201, response.text

    response = requests.post(
        f"{BASE_URL}/attendance/punch-in",
        json={
            "emp_code": emp_code,
            "punched_at": to_millis("2026-10-24", "00:30:00"),
            "status": "PRESENT",
        },
        timeout=10,
    )

    assert response.status_code == 201, response.text

    actual_date = response.json()["date"]

    assert actual_date == "2026-10-23", (
        f"Expected 2026-10-23, got {actual_date}"
    )

    print(
        f"PASS: 00:30 IST on October 24 "
        f"-> attendance date {actual_date}"
    )


def test_punch_out_24_hour_limit():
    print("\nTesting 24-Hour Punch-Out Limit")
    print("-" * 45)

    emp_code = create_employee()

    punch_in = to_millis("2026-10-26", "09:30:00")

    response = requests.post(
        f"{BASE_URL}/attendance/punch-in",
        json={
            "emp_code": emp_code,
            "punched_at": punch_in,
            "status": "PRESENT",
        },
        timeout=10,
    )

    assert response.status_code == 201, response.text

    response = requests.post(
        f"{BASE_URL}/attendance/punch-out",
        json={
            "emp_code": emp_code,
            "punched_at": punch_in + (24 * 60 * 60 * 1000) + 1000,
        },
        timeout=10,
    )

    assert response.status_code == 422, (
        f"Expected HTTP 422, got "
        f"{response.status_code}: {response.text}"
    )

    print("PASS: Punch-out beyond 24 hours rejected (HTTP 422)")

def test_leaderboard_ties():
    print("\nTesting Leaderboard Tie Handling")
    print("-" * 45)

    import uuid

    month = "2027-02"
    date_string = "2027-02-10"

    # Unique department for this test execution
    department = f"QA_{uuid.uuid4().hex[:8]}"

    test_employees = [
        ("10:30:00", 60),
        ("10:10:00", 40),
        ("10:10:00", 40),
        ("09:50:00", 20),
    ]

    created_codes = []

    for punch_time, expected_late in test_employees:

        # Create an employee in our unique department
        emp_code = f"EMP{uuid.uuid4().int % 1000000:06d}"

        employee_response = requests.post(
            f"{BASE_URL}/employees",
            json={
                "emp_code": emp_code,
                "name": "Leaderboard Test Employee",
                "email": f"{uuid.uuid4().hex}@example.com",
                "department": department,
                "shift_start": "09:30",
                "shift_end": "18:30",
                "joined_on": "2026-01-01",
            },
            timeout=10,
        )

        assert employee_response.status_code == 201, (
            f"Employee creation failed: "
            f"{employee_response.text}"
        )

        created_codes.append(emp_code)

        punch_response = requests.post(
            f"{BASE_URL}/attendance/punch-in",
            json={
                "emp_code": emp_code,
                "punched_at": to_millis(date_string, punch_time),
                "status": "PRESENT",
            },
            timeout=10,
        )

        assert punch_response.status_code == 201, (
            f"Punch-in failed: {punch_response.text}"
        )

        actual_late = punch_response.json()["late_minutes"]

        assert actual_late == expected_late, (
            f"{emp_code}: expected {expected_late}, "
            f"got {actual_late}"
        )

    # Request leaderboard with limit=2
    response = requests.get(
        f"{BASE_URL}/analytics/leaderboard/late",
        params={
            "month": month,
            "department": department,
            "limit": 2,
        },
        timeout=10,
    )

    assert response.status_code == 200, response.text

    items = response.json()["items"]

    assert len(items) == 3, (
        f"Expected 3 employees due to tie, "
        f"got {len(items)}: {items}"
    )

    ranks = [item["rank"] for item in items]

    assert ranks == [1, 2, 2], (
        f"Expected [1, 2, 2], got {ranks}"
    )

    actual_codes = {item["emp_code"] for item in items}

    assert actual_codes.issubset(set(created_codes)), (
        "Leaderboard returned employees outside "
        "the test department"
    )

    print("PASS: Tied employees included beyond limit")
    print("PASS: Competition ranks = [1, 2, 2]")

def test_invalid_pagination():
    print("\nTesting Invalid Pagination")
    print("-" * 45)

    tests = [
        ("/employees", {"page": 0}),
        ("/employees", {"page_size": 0}),
        ("/employees", {"page_size": 101}),
        ("/attendance", {"page": 0}),
        ("/attendance", {"page_size": 101}),
    ]

    for endpoint, params in tests:
        response = requests.get(
            f"{BASE_URL}{endpoint}",
            params=params,
            timeout=10,
        )

        assert response.status_code == 422, (
            f"{endpoint} {params}: "
            f"Expected HTTP 422, got {response.status_code}. "
            f"Response: {response.text}"
        )

        print(f"PASS: {endpoint} {params} -> HTTP 422")



if __name__ == "__main__":
    print("=" * 55)
    print("FINAL EDGE-CASE VERIFICATION")
    print("=" * 55)

    test_late_boundary()
    test_overtime_boundary()
    test_work_hours_and_half_day()
    test_overnight_shift()
    test_punch_out_24_hour_limit()
    test_leaderboard_ties()
    test_invalid_pagination()

    print("\nALL EXECUTED EDGE-CASE TESTS PASSED")