# Application Configuration
"""
Configuration module for API Bouncer.
Defines rate limiting policies, Redis connection settings, and violation thresholds.
"""

import os
from typing import Dict
from dataclasses import dataclass


@dataclass
class RateLimitPolicy:
    """Rate limit policy configuration."""
    requests: int  # Number of requests allowed
    window_seconds: int  # Time window in seconds
    burst_size: int  # For token bucket: max burst size


class Config:
    """Application configuration with environment variable support."""
    
    # Redis Configuration
    REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
    REDIS_DB: int = int(os.getenv("REDIS_DB", "0"))
    REDIS_PASSWORD: str = os.getenv("REDIS_PASSWORD", "")
    
    # Redis Key Prefixes (namespacing for clarity)
    REDIS_PREFIX = "api_bouncer"
    SLIDING_WINDOW_PREFIX = f"{REDIS_PREFIX}:sliding_window"
    TOKEN_BUCKET_PREFIX = f"{REDIS_PREFIX}:token_bucket"
    VIOLATION_PREFIX = f"{REDIS_PREFIX}:violations"
    BLOCK_PREFIX = f"{REDIS_PREFIX}:blocked"
    
    # Rate Limit Policies
    # Default policy for most endpoints
    DEFAULT_POLICY = RateLimitPolicy(
        requests=100,
        window_seconds=60,
        burst_size=120  # Allow 20% burst
    )
    
    # Stricter policy for authentication endpoints
    AUTH_POLICY = RateLimitPolicy(
        requests=30,
        window_seconds=60,
        burst_size=35  # Allow small burst
    )
    
    # Route-specific policies
    ROUTE_POLICIES: Dict[str, RateLimitPolicy] = {
        "/auth/login": AUTH_POLICY,
        "/auth/register": AUTH_POLICY,
        "/auth/reset-password": AUTH_POLICY,
    }
    
    # Violation Tracking
    # How many violations before temporary block
    VIOLATION_THRESHOLD: int = 5
    # How long to track violations (seconds)
    VIOLATION_WINDOW: int = 300  # 5 minutes
    # How long to block repeat offenders (seconds)
    BLOCK_DURATION: int = 900  # 15 minutes
    
    # Algorithm Selection
    # Which algorithm to use: "sliding_window" or "token_bucket"
    DEFAULT_ALGORITHM: str = os.getenv("RATE_LIMIT_ALGORITHM", "sliding_window")
    
    @classmethod
    def get_policy_for_route(cls, route_path: str) -> RateLimitPolicy:
        """
        Get the appropriate rate limit policy for a given route.
        
        Args:
            route_path: The API route path
            
        Returns:
            RateLimitPolicy for the route
        """
        return cls.ROUTE_POLICIES.get(route_path, cls.DEFAULT_POLICY)


config = Config()
