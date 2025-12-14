# API Bouncer - Main Application Entry Point
"""
FastAPI application with rate limiting middleware.

This is a demonstration API that shows the rate limiter in action.
Includes sample endpoints with different rate limit policies.
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager

from app.redis_client import redis_client
from app.middleware.rate_limiter import RateLimitMiddleware
from app.config import config


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.
    Handles startup and shutdown events.
    """
    # Startup
    print("🚀 Starting API Bouncer...")
    await redis_client.connect()
    print(f"📊 Using {config.DEFAULT_ALGORITHM} algorithm")
    print(f"⚙️  Default limit: {config.DEFAULT_POLICY.requests} requests per {config.DEFAULT_POLICY.window_seconds}s")
    print(f"🔐 Auth limit: {config.AUTH_POLICY.requests} requests per {config.AUTH_POLICY.window_seconds}s")
    
    yield
    
    # Shutdown
    print("🛑 Shutting down API Bouncer...")
    await redis_client.disconnect()


# Create FastAPI app
app = FastAPI(
    title="API Bouncer",
    description="Production-grade rate limiting middleware for APIs",
    version="1.0.0",
    lifespan=lifespan
)

# Add rate limiting middleware
app.add_middleware(RateLimitMiddleware)


# ============================================================================
# Sample API Endpoints
# ============================================================================

@app.get("/")
async def root():
    """
    Root endpoint - default rate limit applies.
    """
    return {
        "message": "Welcome to API Bouncer",
        "description": "A production-grade rate limiting system",
        "endpoints": {
            "/": "This endpoint (100 req/min)",
            "/api/data": "Sample data endpoint (100 req/min)",
            "/auth/login": "Login endpoint (30 req/min)",
            "/auth/register": "Register endpoint (30 req/min)",
            "/health": "Health check (100 req/min)",
            "/stats": "Rate limit stats for your IP"
        }
    }


@app.get("/health")
async def health_check():
    """
    Health check endpoint.
    """
    return {"status": "healthy", "service": "api-bouncer"}


@app.get("/api/data")
async def get_data():
    """
    Sample data endpoint with default rate limit.
    """
    return {
        "data": [
            {"id": 1, "name": "Item 1"},
            {"id": 2, "name": "Item 2"},
            {"id": 3, "name": "Item 3"},
        ],
        "message": "This endpoint has the default rate limit (100 req/min)"
    }


@app.post("/auth/login")
async def login(request: Request):
    """
    Login endpoint with stricter rate limit (30 req/min).
    This demonstrates route-specific policies.
    """
    return {
        "message": "Login successful",
        "note": "This endpoint has a stricter rate limit (30 req/min) to prevent brute force attacks"
    }


@app.post("/auth/register")
async def register(request: Request):
    """
    Registration endpoint with stricter rate limit (30 req/min).
    """
    return {
        "message": "Registration successful",
        "note": "This endpoint has a stricter rate limit (30 req/min) to prevent spam"
    }


@app.post("/auth/reset-password")
async def reset_password(request: Request):
    """
    Password reset endpoint with stricter rate limit (30 req/min).
    """
    return {
        "message": "Password reset email sent",
        "note": "This endpoint has a stricter rate limit (30 req/min)"
    }


@app.get("/stats")
async def get_stats(request: Request):
    """
    Get rate limit statistics for the current client.
    This is a utility endpoint to help understand rate limiting.
    """
    from app.utils.identifiers import get_client_identifier
    
    identifier = get_client_identifier(request)
    
    return {
        "your_ip": identifier,
        "algorithm": config.DEFAULT_ALGORITHM,
        "policies": {
            "default": {
                "limit": config.DEFAULT_POLICY.requests,
                "window_seconds": config.DEFAULT_POLICY.window_seconds,
                "burst_size": config.DEFAULT_POLICY.burst_size
            },
            "auth": {
                "limit": config.AUTH_POLICY.requests,
                "window_seconds": config.AUTH_POLICY.window_seconds,
                "burst_size": config.AUTH_POLICY.burst_size
            }
        },
        "violation_tracking": {
            "threshold": config.VIOLATION_THRESHOLD,
            "window_seconds": config.VIOLATION_WINDOW,
            "block_duration_seconds": config.BLOCK_DURATION
        }
    }


# ============================================================================
# Error Handlers
# ============================================================================

@app.exception_handler(500)
async def internal_error_handler(request: Request, exc: Exception):
    """
    Handle internal server errors.
    """
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal Server Error",
            "message": "An unexpected error occurred"
        }
    )


if __name__ == "__main__":
    import uvicorn
    
    # Run the application
    # In production, use a proper ASGI server with multiple workers
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,  # Enable auto-reload for development
        log_level="info"
    )
