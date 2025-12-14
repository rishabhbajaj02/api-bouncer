#!/usr/bin/env python3
"""
Test script for API Bouncer rate limiting.

This script demonstrates the rate limiting in action by:
1. Making requests within the limit
2. Exceeding the limit to trigger 429
3. Testing violation tracking and blocking
"""

import asyncio
import time
from typing import List, Dict
import sys

try:
    import httpx
except ImportError:
    print("❌ httpx not installed. Install with: pip install httpx")
    sys.exit(1)


BASE_URL = "http://localhost:8000"
COLORS = {
    "green": "\033[92m",
    "red": "\033[91m",
    "yellow": "\033[93m",
    "blue": "\033[94m",
    "reset": "\033[0m"
}


def print_colored(message: str, color: str):
    """Print colored output."""
    print(f"{COLORS.get(color, '')}{message}{COLORS['reset']}")


async def test_basic_rate_limit():
    """Test basic rate limiting on default endpoint."""
    print_colored("\n🧪 Test 1: Basic Rate Limiting (100 req/min)", "blue")
    print_colored("=" * 60, "blue")
    
    async with httpx.AsyncClient() as client:
        success_count = 0
        rate_limited_count = 0
        
        # Make 105 requests quickly
        for i in range(1, 106):
            try:
                response = await client.get(f"{BASE_URL}/api/data")
                
                if response.status_code == 200:
                    success_count += 1
                    remaining = response.headers.get("X-RateLimit-Remaining", "?")
                    if i % 10 == 0:
                        print_colored(f"✓ Request {i}: Success (Remaining: {remaining})", "green")
                elif response.status_code == 429:
                    rate_limited_count += 1
                    retry_after = response.headers.get("Retry-After", "?")
                    print_colored(f"✗ Request {i}: Rate Limited (Retry After: {retry_after}s)", "red")
                    
            except Exception as e:
                print_colored(f"✗ Request {i}: Error - {e}", "red")
        
        print_colored(f"\n📊 Results:", "blue")
        print_colored(f"  ✓ Successful: {success_count}", "green")
        print_colored(f"  ✗ Rate Limited: {rate_limited_count}", "red")


async def test_auth_endpoint_limit():
    """Test stricter rate limiting on auth endpoints."""
    print_colored("\n🧪 Test 2: Auth Endpoint Limiting (30 req/min)", "blue")
    print_colored("=" * 60, "blue")
    
    async with httpx.AsyncClient() as client:
        success_count = 0
        rate_limited_count = 0
        
        # Make 35 requests to auth endpoint
        for i in range(1, 36):
            try:
                response = await client.post(f"{BASE_URL}/auth/login")
                
                if response.status_code == 200:
                    success_count += 1
                    remaining = response.headers.get("X-RateLimit-Remaining", "?")
                    if i % 5 == 0:
                        print_colored(f"✓ Request {i}: Success (Remaining: {remaining})", "green")
                elif response.status_code == 429:
                    rate_limited_count += 1
                    if rate_limited_count == 1:
                        print_colored(f"✗ Request {i}: First rate limit hit!", "red")
                    
            except Exception as e:
                print_colored(f"✗ Request {i}: Error - {e}", "red")
        
        print_colored(f"\n📊 Results:", "blue")
        print_colored(f"  ✓ Successful: {success_count}", "green")
        print_colored(f"  ✗ Rate Limited: {rate_limited_count}", "red")


async def test_stats_endpoint():
    """Test the stats endpoint to see current configuration."""
    print_colored("\n🧪 Test 3: Stats Endpoint", "blue")
    print_colored("=" * 60, "blue")
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{BASE_URL}/stats")
            if response.status_code == 200:
                data = response.json()
                print_colored(f"✓ Your IP: {data.get('your_ip')}", "green")
                print_colored(f"✓ Algorithm: {data.get('algorithm')}", "green")
                print_colored(f"\n📋 Default Policy:", "blue")
                default = data.get('policies', {}).get('default', {})
                print(f"  - Limit: {default.get('limit')} requests")
                print(f"  - Window: {default.get('window_seconds')} seconds")
                print(f"  - Burst: {default.get('burst_size')} tokens")
                
                print_colored(f"\n📋 Auth Policy:", "blue")
                auth = data.get('policies', {}).get('auth', {})
                print(f"  - Limit: {auth.get('limit')} requests")
                print(f"  - Window: {auth.get('window_seconds')} seconds")
                print(f"  - Burst: {auth.get('burst_size')} tokens")
        except Exception as e:
            print_colored(f"✗ Error: {e}", "red")


async def test_health_check():
    """Test health check endpoint."""
    print_colored("\n🧪 Test 4: Health Check", "blue")
    print_colored("=" * 60, "blue")
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{BASE_URL}/health")
            if response.status_code == 200:
                data = response.json()
                print_colored(f"✓ Status: {data.get('status')}", "green")
                print_colored(f"✓ Service: {data.get('service')}", "green")
            else:
                print_colored(f"✗ Unexpected status: {response.status_code}", "red")
        except Exception as e:
            print_colored(f"✗ Error: {e}", "red")


async def main():
    """Run all tests."""
    print_colored("\n" + "=" * 60, "blue")
    print_colored("🛡️  API Bouncer - Rate Limiting Test Suite", "blue")
    print_colored("=" * 60, "blue")
    
    # Check if API is running
    try:
        async with httpx.AsyncClient() as client:
            await client.get(f"{BASE_URL}/health", timeout=2.0)
    except Exception:
        print_colored("\n❌ API is not running!", "red")
        print_colored("Start the API with: uvicorn app.main:app --reload", "yellow")
        print_colored("And Redis with: docker-compose up -d\n", "yellow")
        return
    
    # Run tests
    await test_health_check()
    await test_stats_endpoint()
    await test_basic_rate_limit()
    
    # Wait a bit before testing auth endpoint
    print_colored("\n⏳ Waiting 5 seconds before auth test...", "yellow")
    await asyncio.sleep(5)
    
    await test_auth_endpoint_limit()
    
    print_colored("\n" + "=" * 60, "blue")
    print_colored("✅ All tests completed!", "green")
    print_colored("=" * 60, "blue")
    print_colored("\n💡 Tips:", "yellow")
    print("  - Check Redis keys: docker exec -it api-bouncer-redis redis-cli KEYS 'api_bouncer:*'")
    print("  - Monitor requests: watch -n 1 'curl -s http://localhost:8000/stats | jq'")
    print("  - Change algorithm: export RATE_LIMIT_ALGORITHM=token_bucket")
    print()


if __name__ == "__main__":
    asyncio.run(main())
