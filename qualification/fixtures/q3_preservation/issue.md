Title:
[Qualification Q3] Extend Counter Without Breaking Existing Behavior

Body:

Purpose:
Extend the existing counter module while preserving its current behavior.

Scope:
Add a decrement operation to the existing counter module.

Expected Behavior:
- Existing increment behavior continues unchanged.
- A decrement operation subtracts one from the supplied integer.

Acceptance Criteria:
1. increment behavior remains unchanged.
2. decrement(1) returns 0.
3. decrement(0) returns -1.
4. Existing tests remain passing.
5. New behavior has automated tests.

Preservation:
The existing increment behavior and its existing regression test
test_increment_existing_behavior must be preserved.

Constraints:
- Python only.
- Existing public behavior must not regress.

Implementation Open Choices:
- Exact internal implementation of decrement is open.
