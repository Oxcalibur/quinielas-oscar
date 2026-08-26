---
description: Independent read-only physical audit before commit authorization.
---

# Physical Audit

Independent read-only physical audit before commit authorization.

## NON-NEGOTIABLE CONTRACT

This workflow is AUDIT ONLY and READ ONLY.

Audit immutability overrides all cleanup, reporting, logging, formatting,
implementation, staging, commit, deployment, and completion instructions.

The auditor must NEVER create, edit, delete, move, rename, format, clean,
stage, unstage, commit, push, or otherwise mutate repository contents.

Finding a defect is NOT authorization to repair it.

Previous conversation context, user statements, previous PASS reports,
implementation summaries, or another agent's report are not sufficient
physical evidence.

The audit verdict MUST be based on current physical evidence obtained during
this invocation.

## DETERMINISTIC EXECUTABLE PREFLIGHT

For executable validation, the auditor MUST run exactly:

    python -B .agents/scripts/physical_audit_preflight.py

The auditor MUST NOT independently execute:

    py_compile
    compileall
    pytest
    python -m pytest
    alternative regression commands

The preflight script is the authoritative executable validation mechanism.

If:

    PREFLIGHT_VERDICT: FAIL

then:

    REGRESSION EVIDENCE: FAIL
    FINAL VERDICT: STOP THE LINE
    READY TO COMMIT: NO

If:

    AUDIT_WORKSPACE_MUTATED: YES

then:

    AUDIT WORKSPACE MUTATED: YES
    FINAL VERDICT: STOP THE LINE
    READY TO COMMIT: NO

No other PASS may override these conditions.

A PREFLIGHT PASS does NOT automatically make the physical audit PASS.

After preflight PASS, the auditor must still physically inspect:

- staged/unstaged source
- actual material test assertions
- canonical production structures
- execution order
- real/fake boundaries
- fail-closed semantics

These inspections must remain observational.

### IMPORTANT ROOT PYTEST SEMANTICS

For this platform repository:

    python -m pytest tests -q

represents the authoritative full platform test scope.

Bare:

    python -m pytest

is NOT an authoritative gate.

`qualification/fixtures/` contains isolated fixture repositories and must not be
treated as platform-root tests.

Do not modify pytest configuration merely to make bare root discovery pass.

---

## 1. AUDIT IMMUTABILITY

The repository workspace is READ ONLY for the complete duration of this audit.

Forbidden actions include:

- creating files
- editing files
- deleting files
- moving or renaming files
- formatting files
- applying fixes
- cleaning scratch/debug artifacts
- git add
- git reset
- git restore
- git clean
- git commit
- git push
- writing reports to disk
- creating temporary evidence files inside the repository
- modifying `.agent-runs/`

### No output redirection

Audit commands must be observational only.

NEVER redirect, pipe-to-file, or persist command output during audit.

Forbidden examples:

```text
git diff > file.txt
git diff >> file.txt
Out-File
Set-Content
Add-Content
Tee-Object when it writes a file
```

## 2. PHYSICAL SOURCE INSPECTION

Never infer correctness from a test PASS or plan summary. You must inspect the actual physical source files.

## 3. ASSERTION INSPECTION

A green test proves only what its assertions actually verify. You must inspect the actual assertions in test files. Forbidden evidence patterns include `assert True`, tests that only prove "no exception", and source-string checks when behavioral verification is possible.

## 4. CANONICAL-SHAPE INSPECTION

Ensure test inputs and objects match actual canonical production structures. Fake object shapes inconsistent with production schemas are forbidden.

## 5. REAL/FAKE INSPECTION

Production functions and real filesystem/git context should be used. Fakes or stubs should only be used when authorized (e.g., external network side effects). Never duplicate production validator logic inside a qualification harness.

## 6. EXECUTION-ORDER INSPECTION

Inspect the real execution order. Never configure something after an operation that already depends on it. Reason explicitly about BEFORE and AFTER execution paths.

## 7. FAIL-CLOSED INSPECTION

Tests that claim fail-closed behavior must actually assert the resulting failure or stop condition, rather than simply passing without side effects.

## 8. REPOSITORY HYGIENE

The repository must be free of unexpected or left-over scratch/debug files.

## 9. STAGING SEMANTICS

All intended modifications must be explicitly staged.

## 10. MANDATORY FINAL REPORT

The final block MUST declare either:
READY FOR COMMIT
or
STOP THE LINE

If the preflight script fails or audit workspace mutated, the verdict MUST be STOP THE LINE.