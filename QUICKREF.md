# API Bouncer - Quick Reference

## 🚀 Quick Start

```bash
# 1. Start Redis
docker-compose up -d

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run the API
uvicorn app.main:app --reload

# 4. Test it
python test_rate_limit.py
```

---

## 📁 Project Structure

```
api-bouncer/
├── app/
│   ├── main.py                 # FastAPI app with sample endpoints
│   ├── config.py               # Configuration and policies
│   ├── redis_client.py         # Redis connection management
│   ├── middleware/
│   │   └── rate_limiter.py     # Rate limiting middleware
│   ├── algorithms/
│   │   ├── sliding_window.py   # Sliding window algorithm
│   │   └── token_bucket.py     # Token bucket algorithm
│   └── utils/
│       └── identifiers.py      # IP extraction utilities
├── docker-compose.yml          # Redis setup
├── requirements.txt            # Python dependencies
├── test_rate_limit.py          # Test script
├── README.md                   # Full documentation
└── DESIGN.md                   # Design decisions
```

---

## 🎯 Key Files

### `app/config.py`
- Rate limit policies (default: 100/min, auth: 30/min)
- Redis connection settings
- Violation thresholds
- Algorithm selection

### `app/algorithms/sliding_window.py`
- Accurate rate limiting using Redis sorted sets
- Stores each request timestamp
- Memory: O(n) per client

### `app/algorithms/token_bucket.py`
- Burst-friendly rate limiting using Redis hash
- Stores token count + last refill time
- Memory: O(1) per client

### `app/middleware/rate_limiter.py`
- FastAPI middleware
- Checks blocks → rate limits → violations
- Adds HTTP headers to responses

---

## 🔧 Configuration

### Environment Variables

```bash
# Redis
export REDIS_HOST=localhost
export REDIS_PORT=6379
export REDIS_DB=0

# Algorithm (sliding_window or token_bucket)
export RATE_LIMIT_ALGORITHM=sliding_window
```

### Modify Policies

Edit `app/config.py`:

```python
# Change default limit
DEFAULT_POLICY = RateLimitPolicy(
    requests=200,        # 200 requests
    window_seconds=60,   # per minute
    burst_size=240       # allow 20% burst
)

# Add custom route policy
ROUTE_POLICIES = {
    "/api/expensive": RateLimitPolicy(
        requests=10,
        window_seconds=60,
        burst_size=12
    )
}
```

---

## 📊 API Endpoints

| Endpoint | Method | Rate Limit | Description |
|----------|--------|------------|-------------|
| `/` | GET | 100/min | Root endpoint |
| `/health` | GET | 100/min | Health check |
| `/stats` | GET | 100/min | Your rate limit info |
| `/api/data` | GET | 100/min | Sample data |
| `/auth/login` | POST | 30/min | Login (stricter) |
| `/auth/register` | POST | 30/min | Register (stricter) |
| `/auth/reset-password` | POST | 30/min | Password reset |

---

## 🧪 Testing

### Manual Testing

```bash
# Make 101 requests to trigger rate limit
for i in {1..101}; do
  curl http://localhost:8000/api/data
done

# Check your stats
curl http://localhost:8000/stats | jq

# Test auth endpoint (stricter limit)
for i in {1..31}; do
  curl -X POST http://localhost:8000/auth/login
done
```

### Automated Testing

```bash
# Run test suite
python test_rate_limit.py

# Install httpx if needed
pip install httpx
```

### Redis Inspection

```bash
# View all keys
docker exec -it api-bouncer-redis redis-cli KEYS 'api_bouncer:*'

# View sliding window data
docker exec -it api-bouncer-redis redis-cli ZRANGE api_bouncer:sliding_window:127.0.0.1:_api_data 0 -1 WITHSCORES

# View token bucket data
docker exec -it api-bouncer-redis redis-cli HGETALL api_bouncer:token_bucket:127.0.0.1:_api_data

# Check if IP is blocked
docker exec -it api-bouncer-redis redis-cli GET api_bouncer:blocked:127.0.0.1

# View violations
docker exec -it api-bouncer-redis redis-cli ZRANGE api_bouncer:violations:127.0.0.1 0 -1 WITHSCORES
```

---

## 🔍 Debugging

### Check Redis Connection

```bash
docker exec -it api-bouncer-redis redis-cli ping
# Should return: PONG
```

### View Redis Logs

```bash
docker logs api-bouncer-redis
```

### Monitor Redis in Real-Time

```bash
docker exec -it api-bouncer-redis redis-cli MONITOR
```

### Check API Logs

The API prints useful information:
- ✓ Connected to Redis
- ⚠️ Blocked IP due to violations
- ✗ Redis errors (if any)

---

## 📈 HTTP Headers

### Success Response (200)

```http
HTTP/1.1 200 OK
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 73
X-RateLimit-Reset: 1702483200
```

### Rate Limited (429)

```http
HTTP/1.1 429 Too Many Requests
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 1702483260
Retry-After: 45

{
  "error": "Too Many Requests",
  "message": "Rate limit exceeded. Please try again later.",
  "retry_after": 45
}
```

### Blocked (429)

```http
HTTP/1.1 429 Too Many Requests
Retry-After: 900

{
  "error": "Temporarily Blocked",
  "message": "Your IP has been temporarily blocked due to repeated rate limit violations.",
  "retry_after": 900
}
```

---

## 🎛️ Switching Algorithms

### Use Sliding Window (default)

```bash
export RATE_LIMIT_ALGORITHM=sliding_window
uvicorn app.main:app --reload
```

### Use Token Bucket

```bash
export RATE_LIMIT_ALGORITHM=token_bucket
uvicorn app.main:app --reload
```

### Compare Algorithms

```bash
# Terminal 1: Sliding Window
RATE_LIMIT_ALGORITHM=sliding_window uvicorn app.main:app --port 8000

# Terminal 2: Token Bucket
RATE_LIMIT_ALGORITHM=token_bucket uvicorn app.main:app --port 8001

# Test both
curl http://localhost:8000/stats  # Sliding Window
curl http://localhost:8001/stats  # Token Bucket
```

---

## 🛠️ Common Tasks

### Reset Rate Limit for Your IP

```bash
# Find your IP
curl http://localhost:8000/stats | jq .your_ip

# Delete Redis keys (replace 127.0.0.1 with your IP)
docker exec -it api-bouncer-redis redis-cli DEL "api_bouncer:sliding_window:127.0.0.1:_api_data"
```

### Unblock an IP

```bash
docker exec -it api-bouncer-redis redis-cli DEL "api_bouncer:blocked:127.0.0.1"
```

### Clear All Rate Limit Data

```bash
docker exec -it api-bouncer-redis redis-cli FLUSHDB
```

### Stop Everything

```bash
# Stop API (Ctrl+C in terminal)

# Stop Redis
docker-compose down

# Remove Redis data
docker-compose down -v
```

---

## 📦 Production Deployment

### Using Docker

```bash
# Build image
docker build -t api-bouncer:latest .

# Run with docker-compose
# Uncomment the 'api' service in docker-compose.yml
docker-compose up -d
```

### Environment Variables for Production

```bash
export REDIS_HOST=redis-cluster.example.com
export REDIS_PORT=6379
export REDIS_PASSWORD=your-secure-password
export RATE_LIMIT_ALGORITHM=sliding_window
```

### Run with Gunicorn (Production ASGI Server)

```bash
pip install gunicorn
gunicorn app.main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

---

## 🐛 Troubleshooting

### "Redis client not initialized"

**Problem:** API started before Redis
**Solution:**
```bash
docker-compose up -d
# Wait 3 seconds
uvicorn app.main:app --reload
```

### "Connection refused to localhost:6379"

**Problem:** Redis not running
**Solution:**
```bash
docker-compose up -d
docker ps  # Verify redis is running
```

### Rate limits not working

**Problem:** Wrong algorithm or Redis data from previous run
**Solution:**
```bash
# Clear Redis
docker exec -it api-bouncer-redis redis-cli FLUSHDB

# Restart API
# Ctrl+C and restart
```

### All requests getting 429

**Problem:** IP might be blocked
**Solution:**
```bash
# Check if blocked
docker exec -it api-bouncer-redis redis-cli GET "api_bouncer:blocked:127.0.0.1"

# Unblock
docker exec -it api-bouncer-redis redis-cli DEL "api_bouncer:blocked:127.0.0.1"
```

---

## 📚 Further Reading

- **README.md** - Full documentation
- **DESIGN.md** - Design decisions and architecture
- **Code comments** - Inline documentation in source files

---

## 🎯 Next Steps

1. ✅ Run the quick start commands
2. ✅ Test with `test_rate_limit.py`
3. ✅ Inspect Redis keys
4. ✅ Try both algorithms
5. ✅ Read DESIGN.md for deep dive
6. ✅ Extend with API keys or metrics

---

**Happy Rate Limiting! 🛡️**
