# Canonical AcceptanceContract Shapes

Use real production model shapes when constructing tests and invariant checks.

Do not replace canonical shapes with convenient simplified representations.

## required_imports

Canonical concept:

required_imports is keyed by FILE PATH.

Example:

required_imports = {
    "storage/model.py": [
        "from pydantic import BaseModel"
    ]
}

Therefore:

WRONG:
search only required_imports.keys() for "pydantic"

CORRECT:
inspect the binding import expressions contained in the values.

## required files

Potential binding file collections include:

required_final_files
required_new_files
required_modified_files
required_deleted_files

When checking one specific path:

- normalize separators
- compare exact normalized paths
- do not use loose substring matching

Example:

storage/schema.py

must NOT automatically match:

storage/schema.py.backup

## required_calls

required_calls may contain nested structures.

Conceptual example:

{
    "module.py": {
        "function_name": [
            {
                "name": "callee",
                "count": 1
            }
        ]
    }
}

Do not assume a flat mapping.

When semantic inspection is required, recursively inspect canonical values or
Pydantic model_dump output.

## required_patterns and required_structures

These may also contain nested values.

Do not inspect only top-level keys.

If qualification must detect whether a technology was converted into a binding
requirement, inspect the actual binding content recursively.

## preserved_behaviors

A PreservedBehavior may contain:

description
affected_files
validation_method
protected_tests

If:

validation_method == "required_test"

a qualification check must not consider an arbitrary non-empty
protected_tests list sufficient proof.

The protected test must be resolvable according to the applicable repository
evidence.

Do NOT globally force every PreservedBehavior to use required_test.

## protected test selectors

Selectors may conceptually look like:

tests/test_counter.py::test_increment_existing_behavior

or:

tests/test_counter.py::TestCounter::test_increment_existing_behavior

For Python qualification, exact test resolution should verify:

- referenced file exists
- Python file parses
- exact final test name exists in the baseline test AST

A substring appearing in a comment or string is not sufficient evidence.

## Quality gate derivation

Do not invent AcceptanceContract fields for behavior that is derived by
production quality-gate logic.

When testing framework selection, use the real production gate derivation
logic.
