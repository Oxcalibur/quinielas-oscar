---
name: sdlc-orchestrator-hardening
description: >
  Performs evidence-driven diagnosis, implementation planning, qualification,
  regression analysis, physical auditing, and hardening of the generic Python
  SDLC Orchestrator. Use when working on AcceptanceContract generation,
  qualification harnesses, Orchestrator defects, regression failures,
  implementation plans, live qualification, physical source audits, or
  pre-commit validation of the SDLC Orchestrator.
---

# SDLC Orchestrator Hardening

Use this skill for engineering, qualification, diagnosis, and auditing of the
generic Python SDLC Orchestrator.

The repository Workspace Rules remain authoritative and always apply.

## 1. Start from physical evidence

Before proposing a change, inspect:

- current source implementation
- relevant tests and their actual assertions
- execution path
- canonical production data structures
- Git state when relevant

Never treat an agent-generated report as sufficient physical evidence.

A test marked PASS proves only what its assertions actually verify.

## 2. Classify ownership before fixing

Classify the defect as one or more of:

- requirement defect
- PO defect
- AcceptanceContract defect
- Orchestrator implementation defect
- qualification harness defect
- test defect
- deployment/integration defect

Do not modify multiple ownership layers unless physical evidence independently
proves each layer defective.

## 3. Characterization before implementation

For a newly observed defect produce:

DEFECT:
OWNER:
PHYSICAL EVIDENCE:
EXPECTED BEHAVIOR:
ACTUAL BEHAVIOR:
EXECUTION PATH:
AUTHORIZED SCOPE:
FROZEN SCOPE:

Do not implement during characterization unless explicitly authorized.

## 4. Implementation-plan contract

Before implementation verify that the plan defines:

- OBJECTIVE
- VERIFIED PHYSICAL EVIDENCE
- AUTHORIZED FILES
- FROZEN FILES
- CURRENT EXECUTION ORDER
- REQUIRED EXECUTION ORDER
- CANONICAL DATA SHAPES
- POSITIVE CASES
- NEGATIVE CASES
- EXACT ASSERTIONS
- VALIDATION COMMANDS
- STOP CONDITIONS

If the plan contains assumptions that can be resolved by reading the
repository, inspect the repository instead of guessing.

## 5. Canonical structures

When AcceptanceContract fields are involved, use their real production shape.

Read:

resources/canonical-contract-shapes.md

before designing contract-related tests or semantic invariant checks.

Never create a simplified fake shape merely because it is easier to test.

## 6. Test quality

For every claimed defect fix require evidence that would fail before the fix
and pass afterward.

Tests must assert their claimed outcome.

Invalid evidence includes:

- assert True
- only proving no exception occurred
- dict lookups whose default value creates PASS
- arbitrary non-empty strings used as evidence of resolution
- source-string assertions when behavioral evidence is practical
- shallow inspection of nested canonical structures
- mocked structures inconsistent with production schemas

Prefer:

INPUT
EXPECTED RESULT
NEGATIVE CASE
POSITIVE CASE
EXACT ASSERTION

## 7. Qualification harness work

For qualification harness tasks read:

resources/qualification-protocol.md

The harness must distinguish:

HARNESS_EXECUTION
from
SCENARIO_VERDICT

A correctly detected Orchestrator defect can legitimately produce:

HARNESS_EXECUTION: PASS
SCENARIO_VERDICT: FAIL

## 8. Real versus fake boundaries

For live qualification, keep real whenever applicable:

- production Contract Generator
- production validators
- production repository-context construction
- configured LLM client
- local filesystem
- local Git

Fake or stub only explicitly external effects such as:

- GitHub mutations
- remote network side effects outside the qualification objective

Never implement a parallel copy of production validator logic.

## 9. Execution-order validation

When moving or inserting behavior, explicitly reconstruct the execution order.

Example:

BEFORE:
git init
-> git add
-> git commit
-> configuration

INVALID because configuration occurs after the operation requiring it.

Correct:

git init
-> configuration
-> git add
-> git commit

Always inspect the actual call order before approving the plan.

## 10. Deterministic before live

Validation order:

1. focused deterministic tests
2. py_compile
3. diff hygiene
4. platform regression suites
5. live Contract qualification
6. E2E qualification only when previous gates permit it
7. physical source audit

Do not use repeated LLM calls to debug a deterministic harness defect.

## 11. Independent audit

Do not authorize a commit from an implementation agent's narrative summary
alone.

For final approval inspect the actual changed source and actual assertions.

A previous PASS report is evidence to verify, not authority.

## 12. Git authorization

Unless explicitly authorized after independent audit:

DO NOT:
- stage
- commit
- push

Keep generated qualification evidence under .agent-runs/ untracked.

## 13. Completion status

Use explicit verdicts:

PASS
FAIL
STOP THE LINE

Only state READY TO COMMIT when physical audit and required validation gates
have passed.

Otherwise state:

READY TO COMMIT: NO
