Title:
[Qualification Q2] Non-Binding Storage Choices

Body:

Purpose:
Create a small persistent record store.

Scope:
The solution must create records, persist them durably, reload them, and
preserve their values exactly.

Expected Behavior:
- Records can be created in memory.
- Records can be updated.
- Records can be saved durably.
- Records can be recovered with equivalent values.

Acceptance Criteria:
1. Record schema supports an identifier and value.
2. Records can be mutated in memory.
3. Records can be persisted.
4. Records can be recovered.
5. Recovered records are equivalent to the persisted records.
6. Automated tests validate the behavior.

Constraints:
- Python only.
- Durable local persistence is required.

Implementation Open Choices:
- Pydantic v2 is recommended but NOT mandatory.
- JSON or SQLite may be used.
- Exact module structure is implementation-defined.

Estimated Files:
- storage/schema.py
- storage/store.py

Estimated Files are NON-BINDING hints and MUST NOT be interpreted as mandatory
file paths.

Recommendations MUST NOT become AcceptanceContract obligations unless another
binding requirement independently requires them.
