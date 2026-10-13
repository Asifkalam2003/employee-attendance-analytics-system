# Employee Attendance & Analytics System

A RESTful backend application built using Python, FastAPI, and MongoDB for managing employee attendance, tracking attendance history, and generating employee and department-level analytics.

The system supports employee management, attendance punch-in and punch-out, attendance regularization, audit history, reporting, and MongoDB aggregation-based analytics.

## Technologies Used

- Python 3
- FastAPI
- MongoDB 6.0+
- PyMongo
- Uvicorn
- Pydantic

## Features

### Employee Management
- Employee creation and validation
- Duplicate employee prevention
- Employee listing with pagination
- Employee filtering and sorting

### Attendance Management
- Employee punch-in and punch-out
- Duplicate attendance prevention
- Attendance status management
- Attendance regularization
- Audit history tracking
- Attendance filtering and pagination

### Attendance Analytics
- Monthly employee attendance analytics
- Department-wise attendance summaries
- Late-arrival leaderboard
- Department attendance trends
- Seven-day moving average calculations

### Additional Features
- MongoDB index optimization
- Concurrency handling
- Request validation and error handling
- MongoDB query execution-plan inspection
- Automated integration and edge-case testing

## Project Structure

```text
candidate_kit/
├── app/
│   ├── __init__.py
│   └── main.py
├── sample_data/
├── DATA_MODEL.md
├── DECISIONS.md
├── openapi.yaml
├── PROBLEM_STATEMENT.docx
├── README.md
├── REVIEW.md
├── requirements.txt
├── sample_seed.py
├── test_integration.py
├── test_edge_cases.py
├── test_performance.py
├── benchmark_performance.py
├── benchmark_monthly.py
├── benchmark_department.py
├── benchmark_leaderboard.py
├── benchmark_trend.py
└── .gitignore
```

## Installation

### 1. Clone the Repository

```bash
git clone <repository-url>
cd candidate_kit
```

Replace `<repository-url>` with the actual GitHub repository URL after publishing the project.

### 2. Create a Virtual Environment

```bash
python -m venv .venv
source .venv/bin/activate
```

On Windows:

```bash
.venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure MongoDB

Ensure MongoDB 6.0 or newer is installed and running.

Create a `.env` file in the project root:

```env
MONGO_URI=mongodb://localhost:27017
MONGO_DB=attendance_db
```

Update these values according to your MongoDB configuration.

Do not commit `.env` or database credentials to GitHub.

### 5. Load Sample Data

```bash
python sample_seed.py
```

### 6. Start the Backend

```bash
uvicorn app.main:app --port 8000 --reload
```

The application will be available at:

http://localhost:8000

## API Documentation

After starting the server, open:

http://localhost:8000/docs

FastAPI provides interactive Swagger UI documentation for testing the API endpoints.

## Main API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| GET | `/health` | Backend health check |
| POST | `/employees` | Create an employee |
| GET | `/employees` | List employees with pagination |
| POST | `/attendance/punch-in` | Record employee punch-in |
| POST | `/attendance/punch-out` | Record employee punch-out |
| PATCH | `/attendance/{emp_code}/{date}` | Regularize attendance |
| GET | `/attendance` | Filter attendance records |
| GET | `/analytics/employees/{emp_code}/monthly` | Monthly employee analytics |
| GET | `/analytics/departments/summary` | Department attendance summary |
| GET | `/analytics/leaderboard/late` | Late-arrival leaderboard |
| GET | `/analytics/departments/{department}/trend` | Department attendance trend |
| GET | `/admin/explain/{endpoint}` | Inspect MongoDB query execution plans |

## Testing and Verification

The application was tested using integration tests, edge-case tests, concurrency tests, and MongoDB query performance benchmarks.

### Integration Testing

Run the automated integration tests:

```bash
python test_integration.py
```

Latest local test results:

| Metric | Result |
|---|---|
| Total tests | 12 |
| Passed | 12 |
| Failed | 0 |

**Result: All 12 integration tests passed.**

The integration tests cover employee creation, duplicate prevention, punch-in, punch-out, attendance filtering, analytics, regularization, and audit history.

### Edge-Case Testing

Run:

```bash
python test_edge_cases.py
```

Latest local test results:

| Metric | Result |
|---|---|
| Total checks | 16 |
| Passed | 16 |
| Failed | 0 |

Edge-case tests include:

- Late-arrival grace-period boundaries
- Overtime calculation boundaries
- Half-day attendance thresholds
- Overnight shift handling
- Punch-out duration validation
- Leaderboard ranking ties
- Invalid pagination parameters

**Result: All 16 edge-case checks passed.**

### Concurrency Testing

Concurrent requests were tested for:

- Employee creation
- Attendance punch-in
- Attendance punch-out
- Attendance regularization

The tests checked duplicate prevention, expected HTTP responses, and audit-history consistency.

### MongoDB Index Verification

MongoDB execution plans were inspected for five operations:

1. Attendance listing
2. Employee monthly analytics
3. Department summary
4. Late-arrival leaderboard
5. Department attendance trend

The execution plans confirmed index usage in the tested scenarios.

## Performance Testing

Performance testing was performed using a separate MongoDB database:

```text
hrone_attendance_performance
```

### Test Dataset

| Metric | Value |
|---|---:|
| Employees | 1,000 |
| Attendance records | 100,000 |
| Departments | 5 |
| Attendance records per employee | 100 |
| Data insertion time | 1.02 seconds |

The dataset was generated using synthetic attendance records.

### Performance Benchmark Results

| Operation | Measured Query Time | Result |
|---|---:|---|
| Attendance listing | 0.50 ms | PASS |
| Monthly employee analytics | 1.49 ms | PASS |
| Department summary | 24.10 ms | PASS |
| Late-arrival leaderboard | 37.34 ms | PASS |
| Department attendance trend | 21.80 ms | PASS |

All five simplified database-level benchmarks completed successfully.

### Attendance Listing Performance

- Total collection size: 100,000 records
- Documents examined: 20
- Records returned: 20
- Index used: `attendance_employee_date_unique`
- Query time: 0.50 ms

MongoDB used the compound employee-date index to retrieve the requested records efficiently.

### Monthly Analytics Performance

- Month tested: January 2026
- Employee: `PERF00001`
- Documents examined: 31
- Index keys examined: 31
- Collection scans: 0
- Query time: 1.49 ms

### Department Summary Performance

- Department: Engineering
- Department headcount: 200
- Attendance records processed: 6,200
- Attendance documents examined: 6,200
- Collection scans: 0
- Query time: 24.10 ms

### Late Leaderboard Performance

- Month tested: January 2026
- Leaderboard entries returned: 10
- Documents examined: 31,000
- Index keys examined: 31,000
- Query time: 37.34 ms

### Department Trend Performance

- Department: Engineering
- Date range: January 1–7, 2026
- Daily trend records returned: 7
- Attendance documents examined: 1,407
- Collection scans: 0
- Query time: 21.80 ms

### Performance Testing Limitations

The benchmark results represent individual executions of simplified MongoDB queries on a local development environment.

They do not represent:

- End-to-end FastAPI response times
- Production load-testing results
- Performance under concurrent user traffic
- Guaranteed response times in other environments

The synthetic dataset was designed for database performance testing and does not reproduce every real-world attendance scenario.

## Running Performance Benchmarks

Generate the performance dataset:

```bash
python test_performance.py
```

The script uses a separate performance database and refuses to populate it if employee or attendance data already exists.

Run the individual benchmarks:

```bash
python benchmark_performance.py
python benchmark_monthly.py
python benchmark_department.py
python benchmark_leaderboard.py
python benchmark_trend.py
```

These benchmarks require the `hrone_attendance_performance` database to contain the generated test dataset.

## Assignment Documentation

| File | Description |
|---|---|
| `PROBLEM_STATEMENT.docx` | Assignment requirements |
| `openapi.yaml` | API contract and business rules |
| `DATA_MODEL.md` | MongoDB data model |
| `DECISIONS.md` | Technical decisions and trade-offs |
| `REVIEW.md` | Implementation review and identified issues |
| `requirements.txt` | Python dependencies |

## Submission

Submit a public GitHub repository containing the required source code, documentation, and relevant tests.

Before submission:

- Ensure all required files are included.
- Verify that the application starts successfully.
- Run the integration and edge-case tests.
- Check that `.gitignore` excludes sensitive and unnecessary files.
- Do not commit `.env`, credentials, virtual environments, or other secrets.

No Dockerfile is required for this assignment.