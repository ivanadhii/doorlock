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
    
    logger.info(f"Logging configured - Level: {log_level}, Debug: {debug}")


# Simple logging functions (NO DECORATORS)
def log_api_request(method: str, path: str, client_ip: str, device_id: str = None, 
                   status_code: int = None, response_time: float = None):
    """Log API request with structured data"""
    
    logger.info(
        f"API {method} {path} - IP: {client_ip} - Device: {device_id or 'N/A'} - "
        f"Status: {status_code or 'N/A'} - Time: {response_time or 0:.3f}s"
    )


def log_device_sync(device_id: str, sync_type: str, status: str, 
                   records_count: int = 0, commands_count: int = 0):
    """Log device sync events"""
    
    logger.info(
        f"Device sync - ID: {device_id} - Type: {sync_type} - Status: {status} - "
        f"Records: {records_count} - Commands: {commands_count}"
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
    
    logger.info(message)


def log_security_event(event_type: str, client_ip: str, details: dict = None):
    """Log security-related events"""
    
    message = f"Security event - Type: {event_type} - IP: {client_ip}"
    if details:
        message += f" - Details: {details}"
    
    logger.warning(message)


# Simple performance logging function (NOT A DECORATOR)
def log_performance_start(operation_name: str):
    """Start performance timing"""
    import time
    return time.time()


def log_performance_end(operation_name: str, start_time: float, success: bool = True):
    """End performance timing and log"""
    import time
    execution_time = time.time() - start_time
    
    if success:
        logger.debug(f"Performance - {operation_name} completed in {execution_time:.3f}s")
    else:
        logger.error(f"Performance - {operation_name} failed after {execution_time:.3f}s")


# Configuration
LOGGING_CONFIG = {
    "level": os.getenv("LOG_LEVEL", "INFO"),
    "debug": os.getenv("DEBUG", "false").lower() == "true",
    "structured": os.getenv("STRUCTURED_LOGGING", "true").lower() == "true",
    "file_logging": os.getenv("FILE_LOGGING", "true").lower() == "true",
    "api_logging": os.getenv("API_LOGGING", "true").lower() == "true",
}