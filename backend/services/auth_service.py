"""
Authentication service and middleware
API key authentication for ESP8266 devices and dashboard
"""

import os
from typing import Optional
from fastapi import Request, Response, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.middleware.base import BaseHTTPMiddleware
from loguru import logger


# API key configuration
API_KEY = os.getenv("API_KEY", "kentutbau123")

# Security scheme
security = HTTPBearer(auto_error=False)

# Protected endpoints that require authentication
PROTECTED_ENDPOINTS = [
    "/api/doorlock/bulk-upload",
    "/api/doorlock/command-ack", 
    "/api/doorlock/commands/",
    "/api/doorlock/command/",
    "/api/firmware/",
    "/api/dashboard/",
]

# Public endpoints that don't require authentication
PUBLIC_ENDPOINTS = [
    "/",
    "/health",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/nginx-status",
]


class AuthMiddleware(BaseHTTPMiddleware):
    """
    API Key authentication middleware
    Validates X-API-Key header for protected endpoints
    """
    
    async def dispatch(self, request: Request, call_next):
        """Process request and validate authentication"""
        
        # Check if endpoint requires authentication
        if not self._requires_auth(request.url.path):
            # Public endpoint, skip authentication
            response = await call_next(request)
            return response
        
        # Extract API key from request
        api_key = self._extract_api_key(request)
        
        if not api_key:
            logger.warning(f"Missing API key for {request.url.path} from {request.client.host}")
            return self._unauthorized_response("Missing API key")
        
        # Validate API key
        if not self._validate_api_key(api_key):
            logger.warning(f"Invalid API key for {request.url.path} from {request.client.host}")
            return self._unauthorized_response("Invalid API key")
        
        # Add authentication info to request state
        request.state.authenticated = True
        request.state.api_key = api_key
        
        # Log successful authentication
        logger.debug(f"Authenticated request: {request.method} {request.url.path}")
        
        # Process request
        response = await call_next(request)
        return response
    
    def _requires_auth(self, path: str) -> bool:
        """Check if endpoint requires authentication"""
        
        # Check public endpoints first
        for public_path in PUBLIC_ENDPOINTS:
            if path.startswith(public_path):
                return False
        
        # Check protected endpoints
        for protected_path in PROTECTED_ENDPOINTS:
            if path.startswith(protected_path):
                return True
        
        # Default to requiring auth for unknown endpoints
        return True
    
    def _extract_api_key(self, request: Request) -> Optional[str]:
        """Extract API key from request headers"""
        
        # Try X-API-Key header (preferred)
        api_key = request.headers.get("X-API-Key")
        if api_key:
            return api_key
        
        # Try Authorization header (Bearer token)
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            return auth_header[7:]  # Remove "Bearer " prefix
        
        # Try API-Key header (alternative)
        api_key = request.headers.get("API-Key")
        if api_key:
            return api_key
        
        return None
    
    def _validate_api_key(self, api_key: str) -> bool:
        """Validate API key against configured key"""
        
        # Simple string comparison for now
        # In production, consider hashing and comparing hashes
        return api_key == API_KEY
    
    def _unauthorized_response(self, message: str) -> Response:
        """Return unauthorized response"""
        
        return Response(
            content=f'{{"error": "{message}", "status_code": 401}}',
            status_code=401,
            headers={"Content-Type": "application/json"}
        )


# Dependency functions for route-level authentication
async def get_current_api_key(request: Request) -> str:
    """
    Dependency to get current API key from request
    Usage: api_key: str = Depends(get_current_api_key)
    """
    
    if not hasattr(request.state, "authenticated") or not request.state.authenticated:
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    return request.state.api_key


async def verify_device_access(request: Request, device_id: str) -> bool:
    """
    Verify that the authenticated request has access to specific device
    For now, all authenticated requests have access to all devices
    In future, implement device-specific API keys
    """
    
    # Check if request is authenticated
    if not hasattr(request.state, "authenticated") or not request.state.authenticated:
        return False
    
    # For now, allow access to all devices for authenticated requests
    # TODO: Implement device-specific access control
    
    logger.debug(f"Device access granted for {device_id}")
    return True


# Rate limiting decorator
def rate_limited(max_requests: int = 60, window_seconds: int = 3600):
    """
    Rate limiting decorator for endpoints
    Usage: @rate_limited(max_requests=10, window_seconds=60)
    """
    
    def decorator(func):
        async def wrapper(*args, **kwargs):
            from utils.redis_client import check_api_rate_limit
            
            # Get request from arguments
            request = None
            for arg in args:
                if isinstance(arg, Request):
                    request = arg
                    break
            
            if not request:
                # If no request found, skip rate limiting
                return await func(*args, **kwargs)
            
            # Use client IP as identifier
            identifier = request.client.host
            
            # Check rate limit
            rate_limit_result = await check_api_rate_limit(
                identifier, max_requests, window_seconds
            )
            
            if not rate_limit_result["allowed"]:
                logger.warning(f"Rate limit exceeded for {identifier}")
                raise HTTPException(
                    status_code=429,
                    detail="Rate limit exceeded",
                    headers={
                        "X-RateLimit-Limit": str(max_requests),
                        "X-RateLimit-Remaining": "0",
                        "X-RateLimit-Reset": str(rate_limit_result.get("reset_in", 0))
                    }
                )
            
            # Add rate limit headers to response
            response = await func(*args, **kwargs)
            
            if hasattr(response, "headers"):
                response.headers["X-RateLimit-Limit"] = str(max_requests)
                response.headers["X-RateLimit-Remaining"] = str(rate_limit_result.get("remaining", 0))
            
            return response
        
        return wrapper
    return decorator


# Authentication utilities
class AuthUtils:
    """Utility functions for authentication and authorization"""
    
    @staticmethod
    def generate_api_key() -> str:
        """Generate a new API key (for future use)"""
        import secrets
        import string
        
        alphabet = string.ascii_letters + string.digits
        return ''.join(secrets.choice(alphabet) for _ in range(32))
    
    @staticmethod
    def hash_api_key(api_key: str) -> str:
        """Hash API key for secure storage (for future use)"""
        import hashlib
        import os
        
        salt = os.getenv("API_KEY_SALT", "doorlock_salt")
        return hashlib.sha256(f"{api_key}{salt}".encode()).hexdigest()
    
    @staticmethod
    def verify_api_key_hash(api_key: str, hash_value: str) -> bool:
        """Verify API key against hash (for future use)"""
        return AuthUtils.hash_api_key(api_key) == hash_value
    
    @staticmethod
    async def log_auth_event(event_type: str, details: dict):
        """Log authentication events for security monitoring"""
        from utils.database import AsyncSessionLocal
        from sqlalchemy import text
        
        try:
            async with AsyncSessionLocal() as session:
                await session.execute(text("""
                    INSERT INTO api_usage (device_id, endpoint, method, status_code, response_time_ms, timestamp)
                    VALUES (:device_id, :endpoint, :method, :status_code, :response_time, NOW())
                """), {
                    "device_id": details.get("device_id"),
                    "endpoint": f"auth:{event_type}",
                    "method": "AUTH",
                    "status_code": details.get("status_code", 200),
                    "response_time": details.get("response_time", 0)
                })
                await session.commit()
                
        except Exception as e:
            logger.error(f"Error logging auth event: {e}")


# Security headers middleware
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses"""
    
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        
        # Add security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        
        # Add CORS headers if needed
        if request.method == "OPTIONS":
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-API-Key"
        
        return response


# Device authentication decorator (for future device-specific auth)
def device_authenticated(func):
    """
    Decorator to ensure device is authenticated and authorized
    Usage: @device_authenticated
    """
    
    async def wrapper(*args, **kwargs):
        # Get device_id from function arguments or path
        device_id = kwargs.get("device_id")
        
        if not device_id:
            # Try to extract from path parameters
            for arg in args:
                if isinstance(arg, Request):
                    path_params = arg.path_params
                    device_id = path_params.get("device_id")
                    break
        
        if not device_id:
            raise HTTPException(status_code=400, detail="Device ID required")
        
        # Verify device access (placeholder for now)
        # In future, implement proper device-specific authentication
        
        return await func(*args, **kwargs)
    
    return wrapper


# Admin authentication (for dashboard)
async def admin_required(request: Request):
    """
    Dependency for admin-only endpoints
    Usage: _: None = Depends(admin_required)
    """
    
    # For now, use same API key for admin access
    # In future, implement separate admin authentication
    
    api_key = await get_current_api_key(request)
    
    # Additional admin checks can be added here
    logger.debug("Admin access granted")
    
    return True


# Authentication configuration
AUTH_CONFIG = {
    "api_key": API_KEY,
    "require_auth": os.getenv("REQUIRE_AUTH", "true").lower() == "true",
    "rate_limit_enabled": os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true",
    "max_requests_per_hour": int(os.getenv("MAX_REQUESTS_PER_HOUR", "1000")),
    "security_headers_enabled": os.getenv("SECURITY_HEADERS_ENABLED", "true").lower() == "true",
}
