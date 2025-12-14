# Rate Limiter Middleware
"""
FastAPI middleware for rate limiting.

This middleware intercepts all requests and enforces rate limits using
the configured algorithm (sliding window or token bucket).

Features:
- Per-IP and per-route rate limiting
- Violation tracking with progressive penalties
- Temporary blocking of repeat offenders
- Standard HTTP 429 responses with headers
- Extensible to API keys and user IDs
"""

import time
from typing import Callable
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.config import config
from app.redis_client import redis_client
from app.utils.identifiers import get_client_identifier, get_route_key
from app.algorithms.sliding_window import SlidingWindowRateLimiter
from app.algorithms.token_bucket import TokenBucketRateLimiter


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Middleware that enforces rate limits on all incoming requests.
    """
    
    def __init__(self, app: ASGIApp, algorithm: str = None):
        """
        Initialize rate limit middleware.
        
        Args:
            app: ASGI application
            algorithm: Rate limiting algorithm to use ("sliding_window" or "token_bucket")
        """
        super().__init__(app)
        self.algorithm = algorithm or config.DEFAULT_ALGORITHM
        
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process each request through rate limiting logic.
        
        Args:
            request: Incoming HTTP request
            call_next: Next middleware/handler in chain
            
        Returns:
            HTTP response (either 429 or from downstream handler)
        """
        # Get client identifier and route
        identifier = get_client_identifier(request)
        route = get_route_key(request)
        
        # Check if client is currently blocked
        is_blocked = await self._is_blocked(identifier)
        if is_blocked:
            return self._create_blocked_response()
        
        # Get rate limit policy for this route
        policy = config.get_policy_for_route(route)
        
        # Get Redis client
        redis = redis_client.get_client()
        
        # Select algorithm
        if self.algorithm == "token_bucket":
            limiter = TokenBucketRateLimiter(redis)
        else:
            limiter = SlidingWindowRateLimiter(redis)
        
        # Check rate limit
        is_allowed, remaining, reset_time = await limiter.is_allowed(
            identifier, route, policy
        )
        
        if not is_allowed:
            # Rate limit exceeded
            # Track violation for progressive blocking
            await self._record_violation(identifier)
            
            # Return 429 Too Many Requests
            return self._create_rate_limit_response(
                remaining=0,
                reset_time=reset_time,
                retry_after=reset_time - int(time.time())
            )
        
        # Request allowed - proceed to handler
        response = await call_next(request)
        
        # Add rate limit headers to response
        response.headers["X-RateLimit-Limit"] = str(policy.requests)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(reset_time)
        
        return response
    
    async def _is_blocked(self, identifier: str) -> bool:
        """
        Check if a client is currently blocked.
        
        Args:
            identifier: Client identifier
            
        Returns:
            True if blocked, False otherwise
        """
        redis = redis_client.get_client()
        block_key = f"{config.BLOCK_PREFIX}:{identifier}"
        
        # Check if block key exists
        is_blocked = await redis.exists(block_key)
        return bool(is_blocked)
    
    async def _record_violation(self, identifier: str) -> None:
        """
        Record a rate limit violation and block if threshold exceeded.
        
        Uses a sliding window to track violations. If a client exceeds
        the violation threshold within the window, they get temporarily blocked.
        
        Args:
            identifier: Client identifier
        """
        redis = redis_client.get_client()
        now = time.time()
        
        # Key for tracking violations
        violation_key = f"{config.VIOLATION_PREFIX}:{identifier}"
        
        # Use sorted set to track violation timestamps
        async with redis.pipeline(transaction=True) as pipe:
            # Remove old violations outside the window
            window_start = now - config.VIOLATION_WINDOW
            pipe.zremrangebyscore(violation_key, 0, window_start)
            
            # Add current violation
            pipe.zadd(violation_key, {str(now): now})
            
            # Count violations in window
            pipe.zcard(violation_key)
            
            # Set TTL
            pipe.expire(violation_key, config.VIOLATION_WINDOW)
            
            results = await pipe.execute()
            violation_count = results[2]
        
        # Check if we should block this client
        if violation_count >= config.VIOLATION_THRESHOLD:
            await self._block_client(identifier)
    
    async def _block_client(self, identifier: str) -> None:
        """
        Temporarily block a client.
        
        Args:
            identifier: Client identifier
        """
        redis = redis_client.get_client()
        block_key = f"{config.BLOCK_PREFIX}:{identifier}"
        
        # Set block key with TTL
        await redis.setex(
            block_key,
            config.BLOCK_DURATION,
            "blocked"
        )
        
        print(f"⚠️  Blocked {identifier} for {config.BLOCK_DURATION}s due to repeated violations")
    
    def _create_rate_limit_response(
        self,
        remaining: int,
        reset_time: int,
        retry_after: int
    ) -> JSONResponse:
        """
        Create a 429 Too Many Requests response.
        
        Args:
            remaining: Remaining requests (0)
            reset_time: Unix timestamp when limit resets
            retry_after: Seconds until client can retry
            
        Returns:
            JSONResponse with 429 status
        """
        return JSONResponse(
            status_code=429,
            content={
                "error": "Too Many Requests",
                "message": "Rate limit exceeded. Please try again later.",
                "retry_after": retry_after
            },
            headers={
                "X-RateLimit-Remaining": str(remaining),
                "X-RateLimit-Reset": str(reset_time),
                "Retry-After": str(retry_after)
            }
        )
    
    def _create_blocked_response(self) -> JSONResponse:
        """
        Create a response for blocked clients.
        
        Returns:
            JSONResponse with 429 status
        """
        return JSONResponse(
            status_code=429,
            content={
                "error": "Temporarily Blocked",
                "message": "Your IP has been temporarily blocked due to repeated rate limit violations.",
                "retry_after": config.BLOCK_DURATION
            },
            headers={
                "Retry-After": str(config.BLOCK_DURATION)
            }
        )
