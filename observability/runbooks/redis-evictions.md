# Redis hot-store evictions elevated

## Symptoms

- `redis_evicted_keys_total` > 0 over a 5-minute window.
- Validator latency climbs because the hot-store cache miss rate rises.

## Dashboard

- Grafana → CollectMind End-to-End → header.
- Redis exporter: `redis_memory_used_bytes`, `redis_maxmemory_bytes`, `redis_evicted_keys_total`.

## Mitigation

1. Inspect Redis memory usage; confirm `maxmemory` is set and `maxmemory-policy` matches operational expectation (`allkeys-lru` for the hot store).
2. Identify the largest keys: `redis-cli --bigkeys`.
3. Scale Redis up (ElastiCache node type) if evictions correlate with legitimate load.

## Escalation

Page the platform on-call. Evictions are not catastrophic but they erode validator latency and SC-004.

## Related ADRs

- (none.)

## Related FRs

- Constitution Principle V — USE metrics for owned resources.
