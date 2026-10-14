"""Pure financial domain logic.

Rules for this package:
- No I/O: no database, HTTP, filesystem, clock, or randomness. Same inputs -> same outputs.
- All amounts are ``Decimal``. Rates are fractions (0.08 == 8%).
- Missing inputs produce an explicit "missing" result; values are never invented or zero-filled.
- Invalid assumptions are rejected by Pydantic validation (``pydantic.ValidationError``).
"""
