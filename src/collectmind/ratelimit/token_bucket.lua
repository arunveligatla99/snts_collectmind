-- token_bucket.lua (feature 002 / T254 / ADR-0008 Part 2)
--
-- Atomic check-and-deduct token bucket in a single EVALSHA round trip.
-- Bucket state is a Redis HASH with two fields:
--   tokens         - current available tokens (float, but stored as string and converted)
--   last_refill_ms - millisecond timestamp of the last successful refill
--
-- Invocation:
--   EVALSHA <sha1> 1 <key> <now_ms> <sustained_rps> <burst_capacity>
--
-- Returns:
--   {1, remaining, 0}            -- allowed; `remaining` tokens left in bucket
--   {0, 0, retry_after_ms}       -- denied; retry after `retry_after_ms` for one token
--
-- Time source: now_ms passed from the caller (NOT redis.call("TIME")). This keeps the
-- script deterministic + replicable across Redis cluster nodes per the Redis Lua
-- scripting contract.
--
-- Atomicity: the entire body is one Redis Lua block; Redis serializes Lua execution
-- server-side. No WATCH/MULTI/EXEC needed (and forbidden per ADR-0008 Part 2 — would be
-- redundant and a code smell). If Redis disconnects mid-script, the bucket state is
-- unchanged because HSET only runs on the final write line.

local key             = KEYS[1]
local now_ms          = tonumber(ARGV[1])
local sustained_rps   = tonumber(ARGV[2])
local burst_capacity  = tonumber(ARGV[3])

if not now_ms or not sustained_rps or not burst_capacity then
  return redis.error_reply("token_bucket.lua: invalid arguments")
end

local state = redis.call("HMGET", key, "tokens", "last_refill_ms")
local tokens         = tonumber(state[1])
local last_refill_ms = tonumber(state[2])

if tokens == nil or last_refill_ms == nil then
  -- Fresh bucket. Start at full burst capacity.
  tokens = burst_capacity
  last_refill_ms = now_ms
end

-- Refill based on elapsed time. Floor to integer tokens so a 1-token-per-N-ms refill
-- is exact and deterministic across nodes (no fractional accumulation drift).
local elapsed_ms = now_ms - last_refill_ms
if elapsed_ms < 0 then
  -- Clock went backwards (NTP correction, etc.). Don't refill; advance the timestamp
  -- so future calls compute against the new wall clock.
  elapsed_ms = 0
end
local refill = math.floor((elapsed_ms * sustained_rps) / 1000)
if refill > 0 then
  tokens = math.min(burst_capacity, tokens + refill)
  -- Advance last_refill_ms by the exact time covered by the refill so we don't lose
  -- sub-1-token elapsed time on the next call.
  last_refill_ms = last_refill_ms + math.floor((refill * 1000) / sustained_rps)
end

if tokens >= 1 then
  tokens = tokens - 1
  -- TTL: keep the bucket key alive for one burst window past the last refill. Buckets
  -- for tenants that go silent eventually expire and free Redis memory. The 2x burst-
  -- window TTL is conservative enough to not lose state under normal traffic gaps.
  local ttl_ms = math.floor((burst_capacity * 1000 * 2) / sustained_rps)
  redis.call("HSET", key, "tokens", tokens, "last_refill_ms", last_refill_ms)
  redis.call("PEXPIRE", key, ttl_ms)
  return {1, tokens, 0}
end

-- Denied. Compute retry hint: time until the next token refills.
-- (1 token at sustained_rps r/s = 1000/sustained_rps ms per token.)
local ms_per_token = math.floor(1000 / sustained_rps)
if ms_per_token < 1 then ms_per_token = 1 end
local retry_after_ms = ms_per_token
-- Persist last_refill_ms even on deny so the next call's refill calculation is correct.
redis.call("HSET", key, "tokens", tokens, "last_refill_ms", last_refill_ms)
return {0, 0, retry_after_ms}
