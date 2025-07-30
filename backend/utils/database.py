"""
Database utilities and connection management
SQLAlchemy setup with async PostgreSQL
"""

import os
from typing import AsyncGenerator, Optional
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy import text
from loguru import logger


# Database configuration
DATABASE_URL = os.getenv(
    "DATABASE_URL", 
    "postgresql+asyncpg://doorlock:doorlock_secure_2025@postgres-db:5432/doorlock_system"
)

# Create async engine
engine = create_async_engine(
    DATABASE_URL,
    echo=os.getenv("DEBUG", "false").lower() == "true",
    pool_size=20,
    max_overflow=30,
    pool_pre_ping=True,
    pool_recycle=3600,
    connect_args={
        "server_settings": {
            "application_name": "doorlock_backend",
        }
    }
)

# Create session maker
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=True,
    autocommit=False
)


class Base(DeclarativeBase):
    """Base class for all database models"""
    pass


async def init_database():
    """Initialize database connection and verify connectivity"""
    try:
        async with engine.begin() as conn:
            # Test connection
            result = await conn.execute(text("SELECT 1"))
            assert result.scalar() == 1
            
            # Check if main tables exist
            result = await conn.execute(text("""
                SELECT COUNT(*) 
                FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name IN ('devices', 'device_status', 'access_logs')
            """))
            table_count = result.scalar()
            
            if table_count >= 3:
                logger.info(f"✅ Database tables verified ({table_count} core tables found)")
            else:
                logger.warning(f"⚠️ Missing database tables (found {table_count}/3)")
                
        logger.info("✅ Database connection established")
        
    except Exception as e:
        logger.error(f"❌ Database initialization failed: {e}")
        raise


async def close_database():
    """Close database connections"""
    try:
        await engine.dispose()
        logger.info("✅ Database connections closed")
    except Exception as e:
        logger.error(f"❌ Error closing database: {e}")


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency to get database session
    Usage: db: AsyncSession = Depends(get_db)
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception as e:
            await session.rollback()
            logger.error(f"Database session error: {e}")
            raise
        finally:
            await session.close()


async def execute_raw_query(query: str, params: Optional[dict] = None):
    """Execute raw SQL query (for complex operations)"""
    async with AsyncSessionLocal() as session:
        try:
            result = await session.execute(text(query), params or {})
            await session.commit()
            return result
        except Exception as e:
            await session.rollback()
            logger.error(f"Raw query error: {e}")
            raise


async def get_database_stats():
    """Get database statistics for monitoring"""
    try:
        async with AsyncSessionLocal() as session:
            # Get table sizes
            result = await session.execute(text("""
                SELECT 
                    schemaname,
                    tablename,
                    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size,
                    pg_total_relation_size(schemaname||'.'||tablename) as size_bytes
                FROM pg_tables 
                WHERE schemaname = 'public'
                ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC
                LIMIT 10
            """))
            
            tables = []
            for row in result:
                tables.append({
                    "table": f"{row.schemaname}.{row.tablename}",
                    "size": row.size,
                    "size_bytes": row.size_bytes
                })
            
            # Get connection stats
            result = await session.execute(text("""
                SELECT 
                    count(*) as total_connections,
                    count(*) FILTER (WHERE state = 'active') as active_connections,
                    count(*) FILTER (WHERE state = 'idle') as idle_connections
                FROM pg_stat_activity 
                WHERE datname = current_database()
            """))
            
            conn_stats = result.first()
            
            # Get database size
            result = await session.execute(text("""
                SELECT pg_size_pretty(pg_database_size(current_database())) as db_size
            """))
            
            db_size = result.scalar()
            
            return {
                "database_size": db_size,
                "connections": {
                    "total": conn_stats.total_connections,
                    "active": conn_stats.active_connections,
                    "idle": conn_stats.idle_connections
                },
                "largest_tables": tables
            }
            
    except Exception as e:
        logger.error(f"Error getting database stats: {e}")
        return {"error": str(e)}


# Health check function
async def check_database_health():
    """Check database health for health endpoint"""
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return {"status": "unhealthy", "database": "disconnected", "error": str(e)}
