# Token Bucket Rate Limiting Algorithm
"""
Token Bucket implementation using Redis Hash.

This algorithm allows controlled bursts while maintaining an average rate.
Tokens are added to a bucket at a fixed rate, and each request consumes one token.

Algorithm:
1. Calculate tokens to add based on time elapsed since last refill
2. Refill bucket (up to max capacity)
3. Try to consume one token
4. Allow request if token was available

Pros:
- Memory efficient (only stores token count and timestamp)
- Allows bursts (good UX for legitimate users)
- Simple and fast

Cons:
- Less precise than sliding window
- Burst allowance can be exploited if not tuned properly

Redis Data Structure:
Key: api_bouncer:token_bucket:{identifier}:{route}
Type: Hash
Fields:
  - tokens: Current token count (float)
  - last_refill: Last refill timestamp (float)
TTL: window_seconds + buffer
"""

import time
import redis.asyncio as redis
from typing import Tuple
from app.config import config, RateLimitPolicy


class TokenBucketRateLimiter:
    """
    Token bucket rate limiter using Redis hash.
    """
    
    def __init__(self, redis_client: redis.Redis):
        """
        Initialize the token bucket rate limiter.
        
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
        Check if a request should be allowed based on token bucket algorithm.
        
        Args:
            identifier: Client identifier (IP, API key, etc.)
            route: Route path being accessed
            policy: Rate limit policy to enforce
            
        Returns:
            Tuple of (is_allowed, remaining_requests, reset_timestamp)
        """
        now = time.time()
        key = self._get_key(identifier, route)
        
        # Calculate refill rate: tokens per second
        refill_rate = policy.requests / policy.window_seconds
        
        # Get current bucket state
        bucket_data = await self.redis.hgetall(key)
        
        if not bucket_data:
            # First request - initialize bucket
            tokens = float(policy.burst_size - 1)  # Consume one token for this request
            last_refill = now
            is_allowed = True
        else:
            # Existing bucket - refill and consume
            tokens = float(bucket_data.get("tokens", 0))
            last_refill = float(bucket_data.get("last_refill", now))
            
            # Calculate tokens to add based on time elapsed
            time_elapsed = now - last_refill
            tokens_to_add = time_elapsed * refill_rate
            
            # Refill bucket (capped at burst_size)
            tokens = min(policy.burst_size, tokens + tokens_to_add)
            
            # Try to consume one token
            if tokens >= 1.0:
                tokens -= 1.0
                is_allowed = True
            else:
                is_allowed = False
        
        # Update bucket state in Redis
        # Use pipeline for atomic update
        async with self.redis.pipeline(transaction=True) as pipe:
            try:
                pipe.hset(
                    key,
                    mapping={
                        "tokens": str(tokens),
                        "last_refill": str(now)
                    }
                )
                pipe.expire(key, policy.window_seconds + 10)
                await pipe.execute()
            except redis.RedisError as e:
                # Fail open on Redis errors
                print(f"Redis error in token bucket: {e}")
                return True, policy.requests, int(now + policy.window_seconds)
        
        # Calculate remaining tokens (rounded down)
        remaining = int(tokens)
        
        # Calculate reset time (when bucket will be full again)
        # Time needed to refill to burst_size
        tokens_needed = policy.burst_size - tokens
        seconds_to_full = tokens_needed / refill_rate if refill_rate > 0 else 0
        reset_time = int(now + seconds_to_full)
        
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
        return f"{config.TOKEN_BUCKET_PREFIX}:{identifier}:{safe_route}"
    
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
