# REVIEW.md

## Defects found in the original starter `app/main.py`

Line numbers refer to the **original starter file** from `SDT_candidate_kit.zip`, not the expanded implementation. The original file has 162 lines.

| # | Where (function / line) | What is wrong | How you'd notice it (test, input, or symptom) | How you fixed it |

|---|---|---|---|---|

| 1 | `compute_late_minutes`, lines 33–37 | Compares a punch-in directly with a clock time on the punch-in date without anchoring to the attendance shift date and IST; overnight shifts are mishandled. | Employee on a 22:00–06:00 shift punches in at 00:30 IST: lateness is computed against 22:00 that same day instead of the previous day's shift. | Determine the attendance/shift date in IST and calculate against the correct scheduled shift start. |

| 2 | `compute_late_minutes`, lines 36–37 | Floors elapsed minutes before checking the 10-minute grace period. A punch at 09:40:01 is incorrectly treated as within grace. | For a 09:30 shift, punch-in at 09:40:01 should have `late_minutes=10`, but the starter returns 0. | Compare elapsed **seconds** to 600 first; when strictly greater, floor total late minutes. |

| 3 | `compute_work_hours`, lines 40–41 | Python `round()` uses ties-to-even rather than the required decimal ROUND_HALF_UP rule. | A duration that produces an exact half-centihour tie can round down instead of up. | Use `Decimal` and `ROUND_HALF_UP` to two decimal places. |

| 4 | `compute_overtime`, lines 44–47 | Always puts shift end on the attendance date; overnight shifts need the following day. | A 22:00–06:00 employee punches out at 06:45 next morning; starter can report hundreds of overtime minutes. | Resolve scheduled shift end using the shift's overnight status and the correct date. |

| 5 | `compute_overtime`, line 47 | Counts overtime of 1–29 minutes, although overtime only counts when at least 30 full minutes beyond shift end. | Punch out 20 minutes after shift end: starter returns 20; required value is 0. | Floor elapsed overtime minutes and apply the 30-minute threshold. |

| 6 | `EmployeeIn`, lines 53–60 | Required fields are plain strings; employee code, email, name/department lengths, dates, and HH:MM shifts are not validated, and equal start/end shifts are accepted. | Create `BAD1`, invalid email, malformed `joined_on`, or equal shift times: starter can accept invalid data. | Add Pydantic field constraints and model validation with 422 responses. |

| 7 | `PunchInIn`, lines 63–66 | Accepts any integer-like timestamp or status without enforcing strict epoch-millisecond bounds and presence-only statuses. | Pass seconds instead of milliseconds, a float/string timestamp, or `status=ABSENT`; starter accepts or mishandles it. | Add strict epoch-millisecond validation and restrict punch-in status to presence statuses. |

| 8 | `health`, lines 72–74 | Returns `ok` without checking whether MongoDB is reachable. | Stop MongoDB and call `/health`: starter still returns HTTP 200. | Ping MongoDB and return HTTP 503 when unavailable. |

| 9 | `create_employee`, lines 77–85 | Check-then-insert is non-atomic and no unique index is created by the starter; concurrent requests can create duplicate employee codes. | Send simultaneous POSTs with the same `emp_code`: more than one may succeed. | Create a unique MongoDB index and translate `DuplicateKeyError` to HTTP 409. |

| 10 | `create_employee`, lines 82–85 | Stores `created_at` as a naive local datetime and returns a Python datetime rather than the contract's epoch-millisecond integer. | POST an employee: `created_at` has the wrong response representation and ambiguous timezone. | Store timezone-aware UTC datetime and serialize timestamps to epoch milliseconds. |

| 11 | `list_employees`, line 93 | Uses `page * page_size` instead of `(page - 1) * page_size`, skipping the first page. | Request `page=1,page_size=5`: starter begins at employee 6. | Correct the skip formula. |

| 12 | `list_employees`, line 94 | Counts all employees even when a department filter is supplied. | Filter by `department=Sales`: `total` still reports the entire collection. | Count documents with the same filter used for the list. |

| 13 | `list_employees`, lines 89–95 | No pagination bounds and no stable `emp_code` ascending sort. | Request `page=0` or `page_size=1000`; ordering may vary between requests. | Validate pagination and sort by `emp_code` ascending in MongoDB. |

| 14 | `punch_in`, lines 100–103 | Does not return 404 when employee is missing; dereferences `emp["shift_start"]` when `emp` is `None`. | Punch in with an unknown employee code: server error instead of HTTP 404. | Explicitly check employee existence and raise HTTP 404. |

| 15 | `punch_in`, lines 102–103 | Uses naive server-local time and derives attendance date without IST/overnight rules. | A timestamp around IST midnight or an overnight shift produces the wrong `date`. | Convert UTC instants to IST and apply the overnight attendance-date rule. |

| 16 | `punch_in`, lines 102, 110–121 | Uses a truthiness check for `punched_at`, stores naive datetimes, and returns raw datetime fields plus an extra `id` rather than contract-compliant epoch-millisecond timestamps. | Provide `punched_at=0`, or inspect a successful response's `punch_in` type and keys. | Validate timestamps strictly, store UTC BSON datetimes, normalize precision, and serialize response timestamps as integer milliseconds without extra IDs. |

| 17 | `punch_in`, lines 104–118 | Duplicate check and insert are separate; without a unique `(emp_code,date)` index, concurrent punch-ins can create duplicate records. | Send simultaneous punch-ins for the same employee and attendance date. | Create the unique compound index and handle duplicate-key conflicts as HTTP 409. |

| 18 | `list_attendance`, lines 124–150 | Reads every matching attendance document into Python, sorts and paginates in memory, and lacks the required secondary sort by employee code. | With ~100,000 records, memory/latency grow; equal-date records are not reliably ordered by `emp_code`. | Apply filtering, `sort(date DESC, emp_code ASC)`, `skip`, and `limit` in MongoDB; create supporting indexes. |

| 19 | `list_attendance`, lines 126–143 | Does not validate date formats, inverted date ranges, status enum, or pagination bounds. | `date_from` later than `date_to`, malformed dates, `page=0`, or invalid status do not reliably produce HTTP 422. | Add typed/explicit request validation and reject invalid filters. |

| 20 | `list_attendance`, lines 144–150 | Returns raw BSON datetimes and `id` fields rather than normalized epoch-millisecond timestamps, including nested history timestamps. | Inspect attendance API response against `openapi.yaml`: timestamp types and extra fields differ. | Recursively serialize BSON datetime values to epoch milliseconds and omit internal identifiers. |

| 21 | Application initialization, lines 20–27 | No index creation is performed for uniqueness, filtering, or analytics; explain plans may require collection scans. | Inspect `db.employees.getIndexes()` / `db.attendance_logs.getIndexes()` or run query explain on a large dataset. | Create idempotent unique and performance indexes during application startup. |

| 22 | Missing `POST /attendance/punch-out`, TODO lines 153–161 | Required punch-out endpoint is absent. | Request returns HTTP 404; work hours, overtime, and half-day cannot be finalized. | Implement timestamp validation, latest eligible open-punch lookup, 24-hour duration rule, derived metrics, and atomic update. |

| 23 | Missing `PATCH /attendance/{emp_code}/{date}`, TODO lines 153–161 | Required regularization endpoint and audit history behavior are absent. | PATCH returns HTTP 404; HR cannot correct attendance or produce an audit entry. | Implement validated correction, derived-field recomputation, optimistic concurrency, and exactly one audit-history append per successful change. |

| 24 | Missing employee monthly analytics, TODO lines 153–161 | Required employee-month report is absent. | Monthly analytics request returns HTTP 404. | Implement MongoDB aggregation for joined-date-aware weekdays, presence, leave, late/overtime totals, and rounded attendance percentage. |

| 25 | Missing department summary analytics, TODO lines 153–161 | Required department summary report is absent. | Department summary request returns HTTP 404. | Implement MongoDB aggregation including eligible employees with no attendance logs and correctly rounded averages. |

| 26 | Missing late leaderboard, TODO lines 153–161 | Required ranked late-arrival leaderboard is absent. | Leaderboard request returns HTTP 404. | Implement MongoDB aggregation, department filter, totals, sorting, and competition ranking for ties. |

| 27 | Missing department trend, TODO lines 153–161 | Required date-by-date trend and trailing seven-day average are absent. | Trend request returns HTTP 404. | Implement MongoDB-based date generation/gap filling, joining-date headcounts, working-day rates, and seven-day moving averages. |

| 28 | Missing admin explain, TODO lines 153–161 | Required execution-plan inspection endpoint is absent. | `/admin/explain/attendance_list` returns HTTP 404. | Implement explain modes that run the corresponding actual queries with `executionStats`. |

## Investigated but not defects

| Area | Observation | Why it is not a defect |

|---|---|---|

| `load_dotenv()` (line 20) | The application reads a local `.env` file. | Loading `.env` is permitted for local development; existing process environment variables retain precedence by default. The `.env` file must not be committed. |

| Default shift times (lines 58–59) | `shift_start` defaults to `09:30` and `shift_end` to `18:30`. | These match the documented defaults; the issue was missing validation, not the defaults. |

| Punch-in's `work_hours=None`, `overtime_minutes=0`, `half_day=False`, `history=[]` (lines 112–116) | These fields are initialized before punch-out. | These are appropriate initial values for an open punch; the incorrect portions were timestamp handling, attendance-date/late calculations, and concurrency. |

| Exact department filtering (lines 91–92) | Filtering uses exact equality rather than case-insensitive matching. | Exact department matching is consistent with the API contract. The actual defect was that `total` ignored this filter. |

| UTC storage versus IST calendar rules | MongoDB datetime values are stored as UTC instants, while attendance dates use IST. | This separation is intentional: timestamps represent absolute instants, and the attendance date is an IST business-calendar value. |

| Weekend trend rates | Weekend `attendance_rate` is `null`, not zero. | The specification defines rates only for working days with a positive headcount; weekend dates still appear in the trend. |

| Zero-log departments | An eligible department may appear with `headcount > 0` and zero attendance counts. | Headcount depends on joining dates, not whether an attendance record exists. |

## Verification performed

- `python test_integration.py`: **12 passed, 0 failed**, covering health, creation/duplicate prevention, punch-in/out and duplicate prevention, attendance filtering, employee monthly analytics, department summary, regularization, and audit history.
- `GET /employees?page=1&page_size=5`: HTTP 200, five ordered items, `total=12`.
- `GET /analytics/leaderboard/late?month=2026-07&limit=10`: HTTP 200; returned one ranked employee with 35 late minutes.
- `GET /analytics/departments/Engineering/trend?from=2026-07-06&to=2026-07-12`: HTTP 200; seven dates, weekend null rates, and correct sample moving averages.
- `GET /admin/explain/attendance_list?emp_code=EMP0001&page=1&page_size=20`: HTTP 200; string search found `IXSCAN` and did not find `COLLSCAN` in this response.

**Verification limits:** These are successful functional and preliminary explain checks, not proof of exhaustive edge-case or high-volume performance compliance. Tie ranking, concurrent race tests, all explain modes, and large-dataset execution plans should be checked separately. The fixes above describe the completed implementation's approach; the original starter file and observed test results are the basis for this review.
