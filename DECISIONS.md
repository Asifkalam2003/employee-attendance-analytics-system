# DECISIONS.md

### 1. Indexes
I created unique indexes on employee codes and attendance
(employee code, date) to prevent duplicates. Other indexes
support department filtering, date sorting, employee punch
lookups, and joining-date queries. I avoided indexing every
field because extra indexes increase storage and write costs.

### 2. Punch-in Race
If two identical punch-in requests arrive together, both
may pass the initial checks. However, MongoDB's unique
(employee code, date) index allows only one insertion.
The successful request returns HTTP 201. The other receives
a duplicate-key error, which my code converts to HTTP 409.

### 3. Ties
The leaderboard uses MongoDB's rank window function.
Employees with equal late minutes receive the same rank.
If two employees tie at the cutoff, both are returned,
even if the result contains more employees than the limit.
This preserves competition ranking.

### 4. Headcount
The department summary starts with the employees collection
instead of attendance logs. It filters employees by joining
date and then looks up attendance records. Therefore,
employees without attendance records still contribute
to the department headcount.

### 5. Scaling
For 100 times more data, I would optimize the department
trend aggregation first. It currently generates employee-day
combinations, which could become expensive. I would consider
precomputed daily summaries while keeping raw attendance
records as the source of truth.