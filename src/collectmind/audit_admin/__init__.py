"""Break-glass audit-admin surface (feature 002 / FR-005a / ADR-0007 Part 5).

Phase 8 ships only the package skeleton. Phase 9 (US1, T237) lands:
    - ``api.py`` — distinct FastAPI router with the break-glass query endpoint.

The router is mounted with ``dependencies=[Depends(authenticated_operator_principal)]`` so
the operator JWT audience claim is verified at the router boundary, before any handler runs.
ADR-0007 Part 5 explains why the distinct-router approach is the build-time-impossibility
guarantee against accidental bypass invocation from the regular audit-query path.
"""
