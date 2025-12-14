# Redis Client Configuration
"""
Async Redis client setup with connection pooling.
Manages Redis lifecycle for the FastAPI application.
"""

from typing import Optional
import redis.asyncio as redis
from app.config import config


class RedisClient:
    """
    Async Redis client wrapper with connection pooling.
    
    This class manages the Redis connection lifecycle and provides
    a single connection pool shared across the application.
    """
    
    def __init__(self):
        self._redis: Optional[redis.Redis] = None
        self._pool: Optional[redis.ConnectionPool] = None
    
    async def connect(self) -> None:
        """
        Initialize Redis connection pool.
        Called during application startup.
        """
        if self._redis is not None:
            return  # Already connected
        
        # Create connection pool for efficient connection reuse
        self._pool = redis.ConnectionPool(
            host=config.REDIS_HOST,
            port=config.REDIS_PORT,
            db=config.REDIS_DB,
            password=config.REDIS_PASSWORD if config.REDIS_PASSWORD else None,
            decode_responses=True,  # Automatically decode bytes to strings
            max_connections=50,  # Pool size for concurrent requests
            socket_connect_timeout=5,
            socket_keepalive=True,
        )
        
        self._redis = redis.Redis(connection_pool=self._pool)
        
        # Test connection
        try:
            await self._redis.ping()
            print(f"✓ Connected to Redis at {config.REDIS_HOST}:{config.REDIS_PORT}")
        except Exception as e:
            print(f"✗ Failed to connect to Redis: {e}")
            raise
    
    async def disconnect(self) -> None:
        """
        Close Redis connection pool.
        Called during application shutdown.
        """
        if self._redis:
            await self._redis.close()
            await self._pool.disconnect()
            self._redis = None
            self._pool = None
            print("✓ Disconnected from Redis")
    
    def get_client(self) -> redis.Redis:
        """
        Get the Redis client instance.
        
        Returns:
            Redis client instance
            
        Raises:
            RuntimeError: If Redis is not connected
        """
        if self._redis is None:
            raise RuntimeError(
                "Redis client not initialized. "
                "Call connect() during application startup."
            )
        return self._redis


# Global Redis client instance
redis_client = RedisClient()


async def get_redis() -> redis.Redis:
    """
    Dependency injection function for FastAPI routes.
    
    Returns:
        Redis client instance
    """
    return redis_client.get_client()
