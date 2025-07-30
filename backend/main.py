#!/usr/bin/env python3
"""
FastAPI Backend for Doorlock IoT System
Main application entry point
"""

import os
import sys
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
import uvicorn
from loguru import logger

# Import application modules
from utils.database import init_database, close_database
from utils.redis_client import init_redis, close_redis
from utils.logger import setup_logging
from services.auth_service import AuthMiddleware
from api.devices import router as devices_router
from api.commands import router as commands_router
from api.firmware import router as firmware_router
from api.dashboard import router as dashboard_router


# Application lifespan management
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown events"""
    # Startup
    logger.info("🚀 Starting Doorlock IoT Backend...")
    
    # Initialize database
    await init_database()
    logger.info("✅ Database initialized")
    
    # Initialize Redis
    await init_redis()
    logger.info("✅ Redis initialized")
    
    logger.info("🎉 Application startup completed!")
    
    yield
    
    # Shutdown
    logger.info("🛑 Shutting down Doorlock IoT Backend...")
    
    # Close connections
    await close_redis()
    await close_database()
    
    logger.info("✅ Application shutdown completed!")


# Create FastAPI application
app = FastAPI(
    title="Doorlock IoT API",
    description="REST API for ESP8266 Doorlock Management System",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan
)

# Add middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["*"]  # Configure for production
)

# Add authentication middleware
app.add_middleware(AuthMiddleware)

# Include routers
app.include_router(devices_router, prefix="/api/doorlock", tags=["devices"])
app.include_router(commands_router, prefix="/api/doorlock", tags=["commands"])
app.include_router(firmware_router, prefix="/api/firmware", tags=["firmware"])
app.include_router(dashboard_router, prefix="/api/dashboard", tags=["dashboard"])


# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint for container orchestration"""
    return {
        "status": "healthy",
        "service": "doorlock-backend",
        "version": "2.0.0",
        "timestamp": asyncio.get_event_loop().time()
    }


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint with API information"""
    return {
        "message": "Doorlock IoT API Server",
        "version": "2.0.0",
        "docs": "/docs",
        "health": "/health",
        "status": "running"
    }


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler for unhandled errors"""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "message": "An unexpected error occurred",
            "request_id": getattr(request.state, "request_id", None)
        }
    )


# HTTP exception handler
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTP exceptions with proper logging"""
    logger.warning(f"HTTP {exc.status_code}: {exc.detail}")
    
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.detail,
            "status_code": exc.status_code,
            "request_id": getattr(request.state, "request_id", None)
        }
    )


# Request middleware for logging
@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    """Log all requests for monitoring"""
    import time
    import uuid
    
    # Generate request ID
    request_id = str(uuid.uuid4())[:8]
    request.state.request_id = request_id
    
    # Log request
    start_time = time.time()
    logger.info(f"[{request_id}] {request.method} {request.url.path}")
    
    # Process request
    response = await call_next(request)
    
    # Log response
    process_time = time.time() - start_time
    logger.info(f"[{request_id}] {response.status_code} - {process_time:.3f}s")
    
    # Add headers
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Process-Time"] = str(process_time)
    
    return response


def main():
    """Main application entry point"""
    # Setup logging
    setup_logging()
    
    # Get configuration from environment
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    debug = os.getenv("DEBUG", "false").lower() == "true"
    workers = int(os.getenv("WORKERS", "1"))
    
    logger.info(f"Starting server on {host}:{port}")
    logger.info(f"Debug mode: {debug}")
    logger.info(f"Workers: {workers}")
    
    # Run server
    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=debug,
        workers=workers if not debug else 1,
        log_level="info" if debug else "warning",
        access_log=debug,
        loop="uvloop" if not debug else "asyncio"
    )


if __name__ == "__main__":
    main()
