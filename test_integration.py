import requests
import time

BASE_URL = "http://127.0.0.1:8000"

passed = 0
failed = 0


def check(name, condition):
    global passed, failed

    if condition:
        print(f"✅ PASS: {name}")
        passed += 1
    else:
        print(f"❌ FAIL: {name}")
        failed += 1


print("\n" + "=" * 55)
print(" EMPLOYEE ATTENDANCE & ANALYTICS SYSTEM")
print(" FINAL INTEGRATION TESTING")
print("=" * 55)


# -------------------------------------
# TEST 1: HEALTH CHECK
# -------------------------------------

response = requests.get(
    f"{BASE_URL}/health",
    timeout=10
)

check(
    "Backend Health Check",
    response.status_code == 200
)


# -------------------------------------
# TEST 2: CREATE EMPLOYEE
# -------------------------------------

import random

emp_code = f"EMP{random.randint(100000, 999999)}"

employee = {
    "emp_code": emp_code,
    "name": "Integration Test Employee",
    "email": f"{emp_code.lower()}@example.com",
    "department": "IT",
    "shift_start": "09:00",
    "shift_end": "18:00",
    "joined_on": "2026-10-01"
}

response = requests.post(
    f"{BASE_URL}/employees",
    json=employee,
    timeout=10
)

check(
    "Employee Creation",
    response.status_code == 201
)

if response.status_code != 201:
    print(response.text)
    raise SystemExit("Employee creation failed.")


# -------------------------------------
# TEST 3: DUPLICATE EMPLOYEE
# -------------------------------------

response = requests.post(
    f"{BASE_URL}/employees",
    json=employee,
    timeout=10
)

check(
    "Duplicate Employee Prevention",
    response.status_code == 409
)


# -------------------------------------
# TEST 4: PUNCH IN
# -------------------------------------

# Verified timestamp from your previous test

punch_in = 1791909000000

attendance_in = {
    "emp_code": emp_code,
    "punched_at": punch_in,
    "status": "PRESENT"
}

response = requests.post(
    f"{BASE_URL}/attendance/punch-in",
    json=attendance_in,
    timeout=10
)

check(
    "Employee Punch-In",
    response.status_code == 201
)


# -------------------------------------
# TEST 5: DUPLICATE PUNCH IN
# -------------------------------------

response = requests.post(
    f"{BASE_URL}/attendance/punch-in",
    json=attendance_in,
    timeout=10
)

check(
    "Duplicate Punch-In Prevention",
    response.status_code == 409
)


# -------------------------------------
# TEST 6: PUNCH OUT
# -------------------------------------

punch_out = 1791937800000

attendance_out = {
    "emp_code": emp_code,
    "punched_at": punch_out
}

response = requests.post(
    f"{BASE_URL}/attendance/punch-out",
    json=attendance_out,
    timeout=10
)

check(
    "Employee Punch-Out",
    response.status_code == 200
)


# -------------------------------------
# TEST 7: DUPLICATE PUNCH OUT
# -------------------------------------

response = requests.post(
    f"{BASE_URL}/attendance/punch-out",
    json=attendance_out,
    timeout=10
)

check(
    "Duplicate Punch-Out Prevention",
    response.status_code == 409
)


# -------------------------------------
# TEST 8: ATTENDANCE FILTERING
# -------------------------------------

response = requests.get(
    f"{BASE_URL}/attendance",
    params={
        "emp_code": emp_code,
        "date_from": "2026-10-13",
        "date_to": "2026-10-13",
        "page": 1,
        "page_size": 20
    },
    timeout=10
)

data = response.json() if response.status_code == 200 else {}

items = data.get("items", [])

check(
    "Attendance Filtering",
    response.status_code == 200
    and len(items) == 1
    and items[0].get("emp_code") == emp_code
)


# -------------------------------------
# TEST 9: MONTHLY EMPLOYEE ANALYTICS
# -------------------------------------

response = requests.get(
    f"{BASE_URL}/analytics/employees/{emp_code}/monthly",
    params={"month": "2026-10"},
    timeout=10
)

data = response.json() if response.status_code == 200 else {}

check(
    "Monthly Employee Analytics",
    response.status_code == 200
    and data.get("emp_code") == emp_code
    and data.get("present_days") == 1
)


# -------------------------------------
# TEST 10: DEPARTMENT ANALYTICS
# -------------------------------------

response = requests.get(
    f"{BASE_URL}/analytics/departments/summary",
    params={
        "month": "2026-10",
        "department": "IT"
    },
    timeout=10
)

data = response.json() if response.status_code == 200 else {}

check(
    "Department Analytics",
    response.status_code == 200
    and isinstance(data.get("items"), list)
    and any(
        item.get("department") == "IT"
        for item in data.get("items", [])
    )
)


# ============================================
# TEST 11: ATTENDANCE REGULARIZATION
# ============================================

print("\nTesting Attendance Regularization...")

# Use the employee and attendance date created
# by your existing integration tests.

attendance_date = "2026-10-13"

regularization_data = {
    "status": "WFH",
    "punch_in": 1791909000000,
    "punch_out": 1791937800000,
    "reason": "Automated integration testing",
    "regularized_by": "HR_ADMIN"
}

response = requests.patch(
    f"{BASE_URL}/attendance/{emp_code}/{attendance_date}",
    json=regularization_data,
    timeout=10
)

check(
    "Attendance Regularization",
    response.status_code == 200
)

if response.status_code == 200:
    result = response.json()

    print("Updated Status:", result.get("status"))
    print("Audit History:", result.get("history"))
else:
    print("Error:", response.text)



# ============================================
# TEST 12: AUDIT HISTORY VERIFICATION
# ============================================

print("\nTesting Audit History...")

if response.status_code == 200:

    history = result.get("history", [])

    check(
        "Audit History Created",
        len(history) > 0
    )

    if history:
        latest_change = history[-1]

        print("Latest Audit Entry:")
        print(latest_change)

else:
    print("Skipping audit history verification.")




# -------------------------------------
# FINAL TEST RESULTS
# -------------------------------------

print("\n" + "=" * 55)
print(" FINAL TEST RESULTS")
print("=" * 55)

print(f"Total Tests: {passed + failed}")
print(f"Passed: {passed}")
print(f"Failed: {failed}")

if failed == 0:
    print("\n✅ ALL EXECUTED INTEGRATION TESTS PASSED!")
else:
    print("\n❌ SOME TESTS FAILED!")

print("=" * 55)

if failed:
    raise SystemExit(1)