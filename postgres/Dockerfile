FROM postgres:15

# Install additional extensions
RUN apt-get update && apt-get install -y \
    postgresql-contrib \
    postgresql-15-cron \
    && rm -rf /var/lib/apt/lists/*

# Copy custom PostgreSQL configuration
COPY config/postgresql.conf /etc/postgresql/postgresql.conf

# Copy initialization scripts
COPY init/ /docker-entrypoint-initdb.d/

# Set proper permissions
RUN chmod -R 755 /docker-entrypoint-initdb.d/

# Expose PostgreSQL port
EXPOSE 5432

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=5 \
    CMD pg_isready -U $POSTGRES_USER -d $POSTGRES_DB || exit 1
