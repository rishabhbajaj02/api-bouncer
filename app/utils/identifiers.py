# Client Identifier Utilities
"""
Utilities for extracting client identifiers from requests.
Supports IP extraction with proxy/load balancer awareness.
"""

from typing import Optional
from fastapi import Request


def get_client_ip(request: Request) -> str:
    """
    Extract the client's IP address from the request.
    
    Handles proxies and load balancers by checking X-Forwarded-For
    and X-Real-IP headers. Falls back to direct client IP.
    
    Args:
        request: FastAPI Request object
        
    Returns:
        Client IP address as string
    """
    # Check X-Forwarded-For header (standard for proxies/load balancers)
    # Format: "client, proxy1, proxy2"
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # Take the first IP (original client)
        return forwarded_for.split(",")[0].strip()
    
    # Check X-Real-IP header (nginx and some other proxies)
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    
    # Fall back to direct client IP
    # request.client can be None in some edge cases (e.g., testing)
    if request.client:
        return request.client.host
    
    # Ultimate fallback
    return "unknown"


def get_client_identifier(request: Request) -> str:
    """
    Get a unique identifier for the client.
    
    Currently uses IP address. Can be extended to support:
    - API keys (from Authorization header)
    - User IDs (from JWT tokens)
    - Custom identifier headers
    
    Args:
        request: FastAPI Request object
        
    Returns:
        Client identifier string
    """
    # For now, use IP address
    # Future: Check for API key in Authorization header
    # Future: Extract user ID from JWT token
    return get_client_ip(request)


def get_route_key(request: Request) -> str:
    """
    Get a normalized route key for rate limiting.
    
    Removes query parameters and normalizes the path.
    
    Args:
        request: FastAPI Request object
        
    Returns:
        Normalized route path
    """
    # Use the route path without query parameters
    # This ensures /api/users?page=1 and /api/users?page=2
    # are treated as the same route
    return request.url.path
