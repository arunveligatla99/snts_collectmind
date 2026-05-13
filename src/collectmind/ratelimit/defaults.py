"""FR-012 verbatim default rate-limit values (feature 002 / T257).

Per spec FR-012 + ADR-0008 Part 1:
    - Inbound endpoint: 2000 r/s sustained, burst 4000 (2x sustained).
    - Query endpoints: 200 r/s sustained, burst 400 (2x sustained).

Binding distinction (FR-012a): the rate limit is NOT the SLO. Feature-001 SC-002
(1000 events/s/tenant sustained at >=99.9% success) is what the system promises a tenant;
the rate limit (2x SC-002) protects shared infrastructure when one tenant misbehaves.
Setting the rate limit equal to the SLO floor would make SLO compliance structurally
unattainable. ``observability/runbooks/ratelimit-sustained-throttle.md`` documents this
distinction and warns future operators against lowering the inbound default to "match
the SLO."
"""

from __future__ import annotations

DEFAULT_INBOUND_SUSTAINED_RPS = 2000
DEFAULT_INBOUND_BURST = 4000
DEFAULT_QUERY_SUSTAINED_RPS = 200
DEFAULT_QUERY_BURST = 400
