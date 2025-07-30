FROM nginx:alpine

# Install additional packages
RUN apk add --no-cache \
    openssl \
    curl \
    && rm -rf /var/cache/apk/*

# Copy custom nginx configuration
COPY nginx.conf /etc/nginx/nginx.conf
COPY conf.d/ /etc/nginx/conf.d/

# Create necessary directories
RUN mkdir -p /var/www/firmware \
    && mkdir -p /var/log/nginx \
    && mkdir -p /etc/nginx/ssl

# Set proper permissions
RUN chown -R nginx:nginx /var/www/firmware \
    && chown -R nginx:nginx /var/log/nginx \
    && chmod -R 755 /var/www/firmware

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost/health || exit 1

# Expose HTTP and HTTPS ports
EXPOSE 80 443
