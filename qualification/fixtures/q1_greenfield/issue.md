Title:
[Qualification Q1] Greenfield Greeting Persistence

Body:

Purpose:
Create a minimal greeting service that can persist and restore its state.

Scope:
Implement the smallest Python solution required to store a person's name,
generate a greeting, persist the state durably to disk, and recover it later.

Expected Behavior:
- A name can be stored in memory.
- A greeting can be generated from that name.
- The state can be written durably to disk.
- The persisted state can be loaded again.
- The recovered name must equal the original name.

Acceptance Criteria:
1. A name can be created and stored.
2. A greeting can be generated from the stored name.
3. State can be persisted durably to disk.
4. Persisted state can be recovered.
5. Recovered state is equivalent to the original state.
6. Automated tests cover the behavior.

Constraints:
- Python only.
- No external service is required.

Implementation Open Choices:
- File format is implementation-defined.
- Class/function structure is implementation-defined.

Estimated Files:
- greeting/service.py
- greeting/storage.py

Estimated Files are NON-BINDING implementation hints.

No specific third-party library is mandatory.
