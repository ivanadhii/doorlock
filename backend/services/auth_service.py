"""
Simple Authentication service
API key authentication for ESP8266 devices
"""

import os
from typing import Optional
from fastapi import Request, Response, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from loguru import logger


# API key configuration
API_KEY = os.getenv("API_KEY", "kentutbau123")

# Protected endpoints that require authentication
PROTECTED_ENDPOINTS = [
    "/api/doorlock/bulk-upload",
    "/api/doorlock/command-ack", 
    "/api/doorlock/commands",
    "/api/doorlock/status",
]

# Public endpoints that don't require authentication
PUBLIC_ENDPOINTS = [
    "/",
    "/health",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/api/doorlock/test",
]


class AuthMiddleware(BaseHTTPMiddleware):
    """Simple API Key authentication middleware"""
    
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
            return self._unauthorized_response("Missing API key")
        
        # Validate API key
        if not self._validate_api_key(api_key):
            return self._unauthorized_response("Invalid API key")
        
        # Add authentication info to request state
        request.state.authenticated = True
        request.state.api_key = api_key
        
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
        
        return None
    
    def _validate_api_key(self, api_key: str) -> bool:
        """Validate API key against configured key"""
        return api_key == API_KEY
    
    def _unauthorized_response(self, message: str) -> Response:
        """Return unauthorized response"""
        return Response(
            content=f'{{"error": "{message}", "status_code": 401}}',
            status_code=401,
            headers={"Content-Type": "application/json"}
        )


# Simple dependency function
async def get_current_api_key(request: Request) -> str:
    """
    Dependency to get current API key from request
    Usage: api_key: str = Depends(get_current_api_key)
    """
    
    if not hasattr(request.state, "authenticated") or not request.state.authenticated:
        raise HTTPException(
            status_code=401,
            detail="Authentication required"
        )
    
    return request.state.api_key


# Simple admin check
async def admin_required(request: Request) -> bool:
    """
    Dependency for admin-only endpoints
    Usage: _: bool = Depends(admin_required)
    """
    
    api_key = await get_current_api_key(request)
    logger.debug("Admin access granted")
    return True