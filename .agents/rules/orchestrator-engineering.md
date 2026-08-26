---
trigger: always_on
---

# SDLC Orchestrator Engineering Rules

These rules ALWAYS apply when working in this repository.

## Core principle

Work evidence-first.

Never infer correctness from:
- an agent report
- a test name
- a PASS label
- an implementation plan

Inspect the physical implementation and actual assertions.

A green test proves only what its assertions actually verify.

## Before changing code

Always:

1. inspect the current physical implementation
2. identify the exact defect
3. identify the execution path affected
4. inspect canonical production data structures
5. define expected positive and negative behavior
6. propose the smallest safe change
7. verify the plan before implementing

Do not begin implementation based only on assumptions.

## Implementation plans

An implementation plan must specify:

- OBJECTIVE
- CURRENT PHYSICAL EVIDENCE
- VERIFIED DEFECT
- AUTHORIZED FILES
- FROZEN FILES
- REQUIRED BEHAVIOR
- CANONICAL DATA SHAPES
- POSITIVE TEST
- NEGATIVE TEST
- EXECUTION ORDER
- VALIDATION
- STOP CONDITIONS

If any material assumption is unresolved, inspect the repository before
implementing rather than guessing.

## Editing policy

EDIT IN PLACE.

Do not recreate or replace complete files unless technically unavoidable.

If full-file replacement is unavoidable:
- preserve all existing behavior
- explain why replacement is necessary
- physically audit the complete replacement afterward

Do not leave scratch/debug files in the repository.

## Test quality

Tests must prove the behavior claimed by their names.

Forbidden evidence patterns:

- assert True
- a test that only proves "no exception"
- PASS obtained through default dictionary values
- source-string checks when behavioral verification is possible
- fake object shapes inconsistent with production schemas
- tests that claim fail-closed behavior without asserting the result

For defect tests prefer:

INPUT
EXPECTED RESULT
NEGATIVE CASE
POSITIVE CASE
ASSERTION

Use canonical production object shapes.

## Real vs fake boundaries

Unless explicitly authorized otherwise:

REAL:
- production functions
- production validators
- local filesystem
- local Git
- repository context
- contract generation during live qualification

FAKE/STUB only when required:
- external GitHub mutations
- external network side effects outside the test scope

Never duplicate production validator logic inside a qualification harness.

## Qualification semantics

Always distinguish:

HARNESS_EXECUTION:
Did the qualification infrastructure execute correctly?

SCENARIO_VERDICT:
Did the Orchestrator satisfy the qualification scenario?

A correctly detected Orchestrator defect may produce:

HARNESS_EXECUTION: PASS
SCENARIO_VERDICT: FAIL

Do not conflate these results.

## Execution-order reasoning

Before inserting or moving a step, inspect the real execution order.

Reason explicitly:

BEFORE:
A -> B -> C

AFTER:
A -> NEW STEP -> B -> C

Never configure something after an operation that already depends on it.

## Ownership

Always distinguish between:

- requirement defect
- PO defect
- AcceptanceContract defect
- Orchestrator implementation defect
- qualification harness defect
- test defect

Do not modify multiple ownership layers simultaneously without physical
evidence that each one is defective.

## Git safety

Unless explicitly authorized by the user:

DO NOT:
- git add
- git commit
- git push
- mutate remote GitHub state

.agent-runs/ must remain untracked.

## Scope safety

When a task is qualification-only, production is frozen.

Do not modify:

- orchestrator.py
- orchestrator_core/*

unless the current task explicitly authorizes production changes.

Do not modify BookAI or PO unless explicitly authorized.

## Completion gate

Before declaring PASS:

1. inspect final physical source
2. run focused tests
3. run required regression tests
4. run py_compile when Python changed
5. run git diff --check
6. inspect git status
7. verify no unexpected files remain
8. verify actual assertions support the claimed PASS

If required evidence is missing:

STOP THE LINE

Never convert missing evidence into PASS.