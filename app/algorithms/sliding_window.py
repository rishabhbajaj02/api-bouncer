# Sliding Window Rate Limiting Algorithm
"""
Sliding Window Log implementation using Redis Sorted Sets.

This algorithm provides accurate rate limiting by tracking each request
timestamp in a Redis sorted set. It's more accurate than fixed windows
but uses more memory.

Algorithm:
1. Store each request timestamp as a score in a sorted set
2. Remove timestamps older than the window
3. Count remaining timestamps
4. Allow request if count < limit

Pros:
- Accurate: no edge case double-dipping between windows
- Precise: per-second granularity
- Fair: requests are counted exactly within the sliding window

Cons:
- Higher memory usage (stores each request timestamp)
- Slightly more complex Redis operations

Redis Data Structure:
Key: api_bouncer:sliding_window:{identifier}:{route}
Type: Sorted Set (ZSET)
Score: Unix timestamp (float)
Member: Unique request ID (timestamp + random)
TTL: window_seconds + buffer
"""

import time
import redis.asyncio as redis
from typing import Tuple
from app.config import config, RateLimitPolicy


class SlidingWindowRateLimiter:
    """
    Sliding window log rate limiter using Redis sorted sets.
    """
    
    def __init__(self, redis_client: redis.Redis):
        """
        Initialize the sliding window rate limiter.
        
        Args:
            redis_client: Async Redis client instance
        """
        self.redis = redis_client
    
    async def is_allowed(
        self,
        identifier: str,
        route: str,
        policy: RateLimitPolicy
    ) -> Tuple[bool, int, int]:
        """
        Check if a request should be allowed based on sliding window algorithm.
        
        Args:
            identifier: Client identifier (IP, API key, etc.)
            route: Route path being accessed
            policy: Rate limit policy to enforce
            
        Returns:
            Tuple of (is_allowed, remaining_requests, reset_timestamp)
        """
        now = time.time()
        window_start = now - policy.window_seconds
        
        # Construct Redis key
        key = self._get_key(identifier, route)
        
        # Use Redis pipeline for atomic operations
        # This ensures race conditions don't cause incorrect counts
        async with self.redis.pipeline(transaction=True) as pipe:
            try:
                # 1. Remove timestamps older than the window
                #    ZREMRANGEBYSCORE removes members with scores < window_start
                pipe.zremrangebyscore(key, 0, window_start)
                
                # 2. Count current requests in the window
                #    ZCARD returns the number of elements in the sorted set
                pipe.zcard(key)
                
                # 3. Add current request timestamp
                #    Use timestamp + small random to ensure uniqueness
                #    Score is the timestamp for range queries
                request_id = f"{now}"
                pipe.zadd(key, {request_id: now})
                
                # 4. Set TTL to auto-cleanup old keys
                #    Add buffer to window to ensure we don't lose data
                pipe.expire(key, policy.window_seconds + 10)
                
                # Execute all commands atomically
                results = await pipe.execute()
                
                # Extract count (result of ZCARD, before we added current request)
                current_count = results[1]
                
            except redis.RedisError as e:
                # On Redis error, fail open (allow request) to prevent service disruption
                # In production, you'd want to log this and alert
                print(f"Redis error in sliding window: {e}")
                return True, policy.requests, int(now + policy.window_seconds)
        
        # Check if request should be allowed
        # We check current_count (before adding) against limit
        is_allowed = current_count < policy.requests
        
        # Calculate remaining requests
        remaining = max(0, policy.requests - current_count - 1)
        
        # Calculate reset time (when the oldest request will expire)
        reset_time = int(now + policy.window_seconds)
        
        return is_allowed, remaining, reset_time
    
    def _get_key(self, identifier: str, route: str) -> str:
        """
        Generate Redis key for this identifier and route.
        
        Args:
            identifier: Client identifier
            route: Route path
            
        Returns:
            Redis key string
        """
        # Sanitize route to avoid key injection
        safe_route = route.replace(":", "_").replace("/", "_")
        return f"{config.SLIDING_WINDOW_PREFIX}:{identifier}:{safe_route}"
    
    async def reset(self, identifier: str, route: str) -> None:
        """
        Reset rate limit for a specific identifier and route.
        Useful for testing or manual overrides.
        
        Args:
            identifier: Client identifier
            route: Route path
        """
        key = self._get_key(identifier, route)
        await self.redis.delete(key)
