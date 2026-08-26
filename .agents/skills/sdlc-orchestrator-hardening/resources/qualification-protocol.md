# Qualification Protocol

## Purpose

The qualification harness exists to certify the SDLC Orchestrator before using
a real product repository as an iterative debugging fixture.

Product repositories must not be used to discover deterministic harness
defects that can be detected locally.

## Qualification layers

Distinguish:

HARNESS_EXECUTION:
Did the qualification infrastructure itself execute correctly and obtain the
required evidence?

SCENARIO_VERDICT:
Did the Orchestrator under test satisfy the qualification scenario?

Examples:

Harness works and Orchestrator violates invariant:

HARNESS_EXECUTION: PASS
SCENARIO_VERDICT: FAIL

Harness cannot obtain required Git evidence:

HARNESS_EXECUTION: FAIL
SCENARIO_VERDICT: FAIL

## Contract qualification

Contract mode should exercise real production:

Issue/context
-> AcceptanceContract generation
-> consistency validation
-> capabilities validation
-> qualification-specific semantic invariants

Qualification-specific invariant logic happens after production validation.

Do not duplicate production validators.

## Live LLM

Ordinary pytest qualification tests must be deterministic and must not call
the LLM.

Live qualification may call the real configured LLM.

Repeated live executions are used to characterize model variability, not to
replace deterministic tests.

## Temporary repositories

Fixture templates are immutable.

Workflow:

fixture template
-> copy to temporary repository
-> initialize real local Git
-> configure local Git identity
-> create baseline commit
-> execute qualification against temporary copy
-> collect evidence
-> destroy temporary copy

Never execute destructive qualification directly against the source fixture.

## Fixture immutability

Capture deterministic fixture fingerprint BEFORE execution.

Capture fingerprint AFTER execution.

If they differ:

HARNESS_EXECUTION: FAIL
STOP THE LINE

## E2E isolation

The real pipeline must execute with the temporary repository as its actual Git
working directory.

Never assume a function argument is a target workspace without verifying its
production signature.

Save original cwd and restore it in finally.

## Git evidence

Git evidence commands must either:

- use check=True
or
- explicitly require returncode == 0

Missing or invalid Git evidence can never produce PASS.

Capture:

baseline HEAD
final HEAD

When successful deployment should commit:

baseline HEAD != final HEAD

Inspect the complete generated range rather than assuming a fixed number of
commits.

## Deployment hygiene

When checking generated commit payload:

new runtime artifacts such as:

*.pyc
__pycache__/

must not be committed.

Baseline-tracked files must not be silently deleted merely because they match
a hygiene pattern.

## Result aggregation

Each run returns a structured result.

For repeated qualification:

ALL runs PASS
-> aggregate PASS

ANY run FAIL
-> aggregate FAIL

CLI exit semantics:

aggregate PASS -> exit 0
aggregate FAIL -> non-zero

## Validation sequence

Use:

1. qualification unit tests
2. py_compile
3. git diff --check
4. platform regression suites
5. live Contract qualification
6. E2E qualification
7. independent physical audit

## Git safety

Qualification development does not authorize:

git add
git commit
git push

unless explicitly granted after independent audit.
