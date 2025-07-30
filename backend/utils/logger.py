"""
Logging configuration and utilities
Structured logging with loguru
"""

import os
import sys
from loguru import logger


def setup_logging():
    """Configure application logging"""
    
    # Remove default logger
    logger.remove()
    
    # Get configuration from environment
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    debug = os.getenv("DEBUG", "false").lower() == "true"
    log_format = os.getenv("LOG_FORMAT", "structured")
    
    # Console logging format
    if debug:
        # Detailed format for development
        console_format = (
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "<level>{message}</level>"
        )
    else:
        # Compact format for production
        console_format = (
            "{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}"
        )
    
    # Add console handler
    logger.add(
        sys.stdout,
        format=console_format,
        level=log_level,
        colorize=True,
        backtrace=debug,
        diagnose=debug
    )
    
    # Add file handler for application logs
    logger.add(
        "/app/logs/backend.log",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}",
        level=log_level,
        rotation="100 MB",
        retention="30 days",
        compression="gz",
        backtrace=True,
        diagnose=True
    )
    
    # Add error file handler
    logger.add(
        "/app/logs/error.log",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}",
        level="ERROR",
        rotation="50 MB",
        retention="90 days",
        compression="gz",
        backtrace=True,
        diagnose=True
    )
    
    # Add API access log handler
    logger.add(
        "/app/logs/api_access.log",
        format="{time:YYYY-MM-DD HH:mm:ss} | {message}",
        filter=lambda record: record["extra"].get("log_type") == "api_access",
        rotation="10 MB",
        retention="7 days"
    )
    
    # Configure log level
    logger.configure(
        handlers=[
            {
                "sink": sys.stdout,
                "level": log_level
            }
        ]
    )
    
    logger.info(f"Logging configured - Level: {log_level}, Debug: {debug}")


# Structured logging functions
def log_api_request(method: str, path: str, client_ip: str, device_id: str = None, 
                   status_code: int = None, response_time: float = None):
    """Log API request with structured data"""
    
    logger.bind(log_type="api_access").info(
        f"API {method} {path} - IP: {client_ip} - Device: {device_id or 'N/A'} - "
        f"Status: {status_code or 'N/A'} - Time: {response_time or 0:.3f}s"
    )


def log_device_sync(device_id: str, sync_type: str, status: str, 
                   records_count: int = 0, commands_count: int = 0):
    """Log device sync events"""
    
    logger.info(
        f"Device sync - ID: {device_id} - Type: {sync_type} - Status: {status} - "
        f"Records: {records_count} - Commands: {commands_count}",
        extra={
            "log_type": "device_sync",
            "device_id": device_id,
            "sync_type": sync_type,
            "status": status,
            "records_count": records_count,
            "commands_count": commands_count
        }
    )


def log_ota_event(device_id: str, event_type: str, firmware_version: str = None, 
                 progress: int = None, error: str = None):
    """Log OTA update events"""
    
    message = f"OTA {event_type} - Device: {device_id}"
    if firmware_version:
        message += f" - Version: {firmware_version}"
    if progress is not None:
        message += f" - Progress: {progress}%"
    if error:
        message += f" - Error: {error}"
    
    logger.info(
        message,
        extra={
            "log_type": "ota_event",
            "device_id": device_id,
            "event_type": event_type,
            "firmware_version": firmware_version,
            "progress": progress,
            "error": error
        }
    )


def log_security_event(event_type: str, client_ip: str, details: dict = None):
    """Log security-related events"""
    
    message = f"Security event - Type: {event_type} - IP: {client_ip}"
    if details:
        message += f" - Details: {details}"
    
    logger.warning(
        message,
        extra={
            "log_type": "security",
            "event_type": event_type,
            "client_ip": client_ip,
            "details": details or {}
        }
    )


def log_database_event(operation: str, table: str, records_affected: int = None, 
                      execution_time: float = None, error: str = None):
    """Log database operations"""
    
    level = "ERROR" if error else "DEBUG"
    message = f"Database {operation} - Table: {table}"
    
    if records_affected is not None:
        message += f" - Records: {records_affected}"
    if execution_time is not None:
        message += f" - Time: {execution_time:.3f}s"
    if error:
        message += f" - Error: {error}"
    
    logger.log(
        level,
        message,
        extra={
            "log_type": "database",
            "operation": operation,
            "table": table,
            "records_affected": records_affected,
            "execution_time": execution_time,
            "error": error
        }
    )


def log_cache_event(operation: str, cache_type: str, key: str = None, 
                   hit: bool = None, execution_time: float = None):
    """Log cache operations"""
    
    message = f"Cache {operation} - Type: {cache_type}"
    if key:
        message += f" - Key: {key}"
    if hit is not None:
        message += f" - Hit: {hit}"
    if execution_time is not None:
        message += f" - Time: {execution_time:.3f}s"
    
    logger.debug(
        message,
        extra={
            "log_type": "cache",
            "operation": operation,
            "cache_type": cache_type,
            "key": key,
            "hit": hit,
            "execution_time": execution_time
        }
    )


# Performance monitoring decorator
def log_performance(operation_name: str):
    """Decorator to log function performance"""
    
    def decorator(func):
        import asyncio
        import time
        from functools import wraps
        
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                execution_time = time.time() - start_time
                
                logger.debug(
                    f"Performance - {operation_name} completed in {execution_time:.3f}s",
                    extra={
                        "log_type": "performance",
                        "operation": operation_name,
                        "execution_time": execution_time,
                        "status": "success"
                    }
                )
                return result
                
            except Exception as e:
                execution_time = time.time() - start_time
                
                logger.error(
                    f"Performance - {operation_name} failed after {execution_time:.3f}s: {e}",
                    extra={
                        "log_type": "performance", 
                        "operation": operation_name,
                        "execution_time": execution_time,
                        "status": "error",
                        "error": str(e)
                    }
                )
                raise
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                execution_time = time.time() - start_time
                
                logger.debug(
                    f"Performance - {operation_name} completed in {execution_time:.3f}s",
                    extra={
                        "log_type": "performance",
                        "operation": operation_name,
                        "execution_time": execution_time,
                        "status": "success"
                    }
                )
                return result
                
            except Exception as e:
                execution_time = time.time() - start_time
                
                logger.error(
                    f"Performance - {operation_name} failed after {execution_time:.3f}s: {e}",
                    extra={
                        "log_type": "performance",
                        "operation": operation_name,
                        "execution_time": execution_time,
                        "status": "error",
                        "error": str(e)
                    }
                )
                raise
        
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


# Log filtering utilities
class LogFilter:
    """Utilities for filtering and analyzing logs"""
    
    @staticmethod
    def get_device_logs(device_id: str, hours: int = 24):
        """Get logs for specific device (placeholder - implement with log aggregation)"""
        # This would typically integrate with a log aggregation system
        # For now, return placeholder
        return {
            "device_id": device_id,
            "hours": hours,
            "message": "Log filtering not implemented - use external log aggregation"
        }
    
    @staticmethod
    def get_error_summary(hours: int = 1):
        """Get error summary (placeholder - implement with log aggregation)"""
        return {
            "hours": hours,
            "message": "Error summary not implemented - use external log aggregation"
        }


# Configuration
LOGGING_CONFIG = {
    "level": os.getenv("LOG_LEVEL", "INFO"),
    "debug": os.getenv("DEBUG", "false").lower() == "true",
    "structured": os.getenv("STRUCTURED_LOGGING", "true").lower() == "true",
    "file_logging": os.getenv("FILE_LOGGING", "true").lower() == "true",
    "api_logging": os.getenv("API_LOGGING", "true").lower() == "true",
}
