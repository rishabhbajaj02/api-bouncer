# API Bouncer - Design Decisions & Architecture

## Executive Summary

This document explains the key architectural and implementation decisions made in building the API Bouncer rate limiting system.

---

## 1. Algorithm Selection

### Why Two Algorithms?

**Sliding Window Log** and **Token Bucket** serve different use cases:

| Use Case | Best Algorithm | Reason |
|----------|---------------|---------|
| Strict API limits | Sliding Window | No burst exploitation |
| User-facing APIs | Token Bucket | Better UX, allows bursts |
| Payment/billing APIs | Sliding Window | Accurate counting |
| Public APIs | Token Bucket | Forgiving to legitimate users |

### Implementation Details

**Sliding Window:**
- Uses Redis Sorted Sets (ZSET)
- Each request is a member with timestamp as score
- `ZREMRANGEBYSCORE` removes old requests atomically
- `ZCARD` counts current requests
- Memory: O(n) where n = requests in window

**Token Bucket:**
- Uses Redis Hash
- Stores: `{tokens: float, last_refill: timestamp}`
- Calculates refill based on time elapsed
- Memory: O(1) - constant space per client

---

## 2. Redis Design Choices

### Key Naming Strategy

```
api_bouncer:sliding_window:{ip}:{route}
api_bouncer:token_bucket:{ip}:{route}
api_bouncer:violations:{ip}
api_bouncer:blocked:{ip}
```

**Why this structure?**
- **Namespacing**: `api_bouncer:` prefix prevents key collisions
- **Algorithm separation**: Easy to switch or run both
- **Granularity**: Per-IP and per-route for fine control
- **Debuggability**: Easy to inspect in Redis CLI

### Atomic Operations

**Critical sections use pipelines:**
```python
async with redis.pipeline(transaction=True) as pipe:
    pipe.zremrangebyscore(key, 0, window_start)
    pipe.zcard(key)
    pipe.zadd(key, {request_id: now})
    pipe.expire(key, ttl)
    results = await pipe.execute()
```

**Why?**
- Prevents race conditions in concurrent requests
- Ensures consistency across multiple API instances
- Atomic read-modify-write operations

### TTL Strategy

Every key has a TTL:
- Rate limit keys: `window_seconds + 10` (buffer for cleanup)
- Violation keys: `VIOLATION_WINDOW` (5 minutes)
- Block keys: `BLOCK_DURATION` (15 minutes)

**Why?**
- Automatic cleanup - no manual garbage collection
- Prevents Redis memory bloat
- Self-healing system

---

## 3. Middleware Architecture

### Why Middleware?

FastAPI middleware intercepts **all requests** before they reach route handlers.

**Benefits:**
- ✅ Centralized rate limiting logic
- ✅ No code duplication across routes
- ✅ Easy to enable/disable globally
- ✅ Consistent behavior

**Alternative considered:** Dependency injection per route
- ❌ Requires manual application to each route
- ❌ Easy to forget on new routes
- ❌ More boilerplate

### Request Flow

```
1. Request arrives
2. Middleware extracts IP and route
3. Check if IP is blocked → 429 if yes
4. Check rate limit → 429 if exceeded
5. Record violation if limit exceeded
6. Pass to route handler if allowed
7. Add rate limit headers to response
```

---

## 4. Violation Tracking & Progressive Blocking

### Why Track Violations?

Simple rate limiting isn't enough for malicious actors:
- They can repeatedly hit the limit
- Each violation is a wasted Redis operation
- Legitimate users get slower responses

**Solution:** Progressive penalties
1. First violation: 429 response
2. 5 violations in 5 minutes: 15-minute block
3. Block prevents all requests (checked before rate limit)

### Implementation

Uses the same sliding window technique:
```python
violation_key = f"api_bouncer:violations:{ip}"
# Sorted set of violation timestamps
# If count >= threshold → block
```

**Why sorted set?**
- Reuses sliding window logic
- Accurate violation counting
- Automatic cleanup via TTL

---

## 5. Error Handling Strategy

### Fail-Open vs Fail-Closed

**Decision: Fail-Open**

If Redis is unavailable:
```python
except redis.RedisError as e:
    print(f"Redis error: {e}")
    return True, policy.requests, reset_time  # Allow request
```

**Why fail-open?**
- ✅ API remains available during Redis outage
- ✅ Better user experience
- ✅ Rate limiting is a protection, not a core feature

**Trade-off:**
- ❌ Temporary loss of rate limiting during outage
- ⚠️ Acceptable for most use cases
- ⚠️ Production should have Redis HA (Sentinel/Cluster)

**When to fail-closed:**
- Payment processing APIs
- APIs with strict compliance requirements
- When rate limiting is contractual (billing)

---

## 6. HTTP Headers

### Standard Headers

```http
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 73
X-RateLimit-Reset: 1702483200
Retry-After: 45
```

**Why these headers?**
- Industry standard (GitHub, Twitter, Stripe use them)
- Helps clients implement backoff strategies
- Transparent to developers using the API

### Header Calculation

**Remaining:**
- Sliding Window: `limit - current_count - 1`
- Token Bucket: `int(tokens)`

**Reset:**
- Sliding Window: `now + window_seconds`
- Token Bucket: `now + time_to_refill_full`

---

## 7. Configuration Design

### Environment Variables

```python
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
RATE_LIMIT_ALGORITHM = os.getenv("RATE_LIMIT_ALGORITHM", "sliding_window")
```

**Why env vars?**
- ✅ 12-factor app compliance
- ✅ Easy to change without code changes
- ✅ Different configs for dev/staging/prod

### Policy Configuration

```python
ROUTE_POLICIES: Dict[str, RateLimitPolicy] = {
    "/auth/login": AUTH_POLICY,
    "/auth/register": AUTH_POLICY,
}
```

**Why route-specific policies?**
- Different endpoints have different risk profiles
- Auth endpoints need stricter limits (brute force)
- Public endpoints can be more lenient

---

## 8. Scalability Considerations

### Horizontal Scaling

**Current design supports:**
- Multiple API instances sharing Redis
- Connection pooling (50 connections per instance)
- Atomic operations prevent race conditions

**Production setup:**
```
Load Balancer
    ├── API Instance 1 ──┐
    ├── API Instance 2 ──┼── Redis Cluster
    └── API Instance 3 ──┘
```

### Performance Characteristics

**Latency:**
- Sliding Window: ~1-2ms (4 Redis ops)
- Token Bucket: ~0.5-1ms (2 Redis ops)

**Memory:**
- Sliding Window: ~100 bytes per request
- Token Bucket: ~50 bytes per client

**Throughput:**
- Single Redis: 100,000+ ops/sec
- With pipelining: 1,000,000+ ops/sec

### Optimization Strategies

1. **Use Token Bucket for high-traffic endpoints**
2. **Increase connection pool size** for more concurrent requests
3. **Use Redis Cluster** for horizontal Redis scaling
4. **Add caching** for policy lookups (currently hits config)
5. **Batch operations** where possible

---

## 9. Security Considerations

### IP Extraction

```python
# Check X-Forwarded-For (proxy/load balancer)
# Check X-Real-IP (nginx)
# Fallback to direct client IP
```

**Why this order?**
- Handles reverse proxies correctly
- Works with load balancers
- Prevents IP spoofing (trust proxy headers)

**Production consideration:**
- Validate proxy headers
- Only trust from known proxy IPs
- Use `X-Forwarded-For` first IP only

### Key Injection Prevention

```python
safe_route = route.replace(":", "_").replace("/", "_")
```

**Why sanitize?**
- Prevents Redis key injection
- Ensures predictable key structure
- Defense in depth

---

## 10. Testing Strategy

### Test Script Features

1. **Health check** - Verify API is running
2. **Stats endpoint** - Inspect configuration
3. **Basic rate limiting** - Test default policy
4. **Auth endpoint** - Test stricter policy
5. **Colored output** - Easy to read results

### Manual Testing

```bash
# View Redis keys
docker exec -it api-bouncer-redis redis-cli KEYS 'api_bouncer:*'

# Inspect sliding window
docker exec -it api-bouncer-redis redis-cli ZRANGE api_bouncer:sliding_window:127.0.0.1:_api_data 0 -1 WITHSCORES

# Check if IP is blocked
docker exec -it api-bouncer-redis redis-cli GET api_bouncer:blocked:127.0.0.1
```

---

## 11. Extension Points

### Where to Add Features

**1. API Key Support:**
- Modify `app/utils/identifiers.py::get_client_identifier()`
- Check `Authorization` header
- Return `f"api_key:{key}"` instead of IP

**2. User-Based Limits:**
- Decode JWT token in identifier extraction
- Use user ID as identifier
- Store per-user policies in Redis/DB

**3. Metrics:**
- Add Prometheus counters in middleware
- Track: hits, blocks, latency
- Export on `/metrics` endpoint

**4. Dynamic Policies:**
- Store policies in Redis/database
- Load on startup or cache with TTL
- Allow runtime updates via admin API

**5. Geolocation:**
- Add IP geolocation lookup
- Apply stricter limits to high-risk countries
- Use MaxMind GeoIP2 database

---

## 12. Production Checklist

Before deploying to production:

- [ ] Set up Redis Cluster or Sentinel for HA
- [ ] Configure proper connection pool size
- [ ] Add monitoring (Prometheus + Grafana)
- [ ] Set up alerts for high block rates
- [ ] Implement structured logging
- [ ] Add distributed tracing (OpenTelemetry)
- [ ] Review and tune rate limit policies
- [ ] Test failover scenarios
- [ ] Document runbooks for common issues
- [ ] Set up Redis backups (if using persistence)
- [ ] Configure proper CORS headers
- [ ] Add API key authentication
- [ ] Implement admin endpoints for overrides
- [ ] Load test with expected traffic patterns

---

## 13. Lessons Learned

### What Worked Well

1. **Middleware pattern** - Clean separation of concerns
2. **Redis pipelines** - Atomic operations prevent bugs
3. **Two algorithms** - Flexibility for different use cases
4. **Fail-open** - Better UX during outages
5. **Violation tracking** - Effective against persistent abuse

### What Could Be Improved

1. **Metrics** - Should be built-in, not an extension
2. **Admin API** - Manual overrides are common in production
3. **Testing** - Unit tests would catch edge cases
4. **Documentation** - Inline code comments could be more detailed
5. **Observability** - Structured logging from day one

### Alternative Approaches Considered

1. **Fixed Window** - Simpler but has edge case issues
2. **Leaky Bucket** - Similar to token bucket, more complex
3. **Sliding Window Counter** - Hybrid approach, less accurate
4. **In-Memory** - Doesn't scale horizontally
5. **Database** - Too slow for rate limiting

---

## Conclusion

The API Bouncer demonstrates production-grade rate limiting with:
- ✅ Strong system design (middleware, strategy pattern)
- ✅ Distributed coordination (Redis)
- ✅ Security-first thinking (violation tracking, blocking)
- ✅ Clear separation of concerns
- ✅ Production-ready patterns (connection pooling, error handling)

This project serves as a foundation for real-world rate limiting systems and can be extended with API keys, metrics, and dynamic policies.

---

**Author's Note:** This is a learning project that prioritizes clarity and educational value. In a production system, you might use battle-tested libraries like `slowapi` or `fastapi-limiter`, but building from scratch teaches the underlying principles that make you a better engineer.
