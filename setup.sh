#!/bin/bash

# =================================
# DOORLOCK IoT SYSTEM - SETUP SCRIPT
# =================================

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging function
log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')] INFO: $1${NC}"
}

warn() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] WARN: $1${NC}"
}

error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ERROR: $1${NC}"
    exit 1
}

# Check if running as root
check_root() {
    if [[ $EUID -eq 0 ]]; then
        warn "Running as root. Consider using a non-root user with docker permissions."
    fi
}

# Check system requirements
check_requirements() {
    log "Checking system requirements..."
    
    # Check Docker
    if ! command -v docker &> /dev/null; then
        error "Docker is not installed. Please install Docker first."
    fi
    
    # Check Docker Compose
    if ! command -v docker-compose &> /dev/null; then
        error "Docker Compose is not installed. Please install Docker Compose first."
    fi
    
    # Check available disk space (minimum 10GB)
    available_space=$(df . | tail -1 | awk '{print $4}')
    min_space=$((10 * 1024 * 1024)) # 10GB in KB
    
    if [[ $available_space -lt $min_space ]]; then
        error "Insufficient disk space. At least 10GB required."
    fi
    
    # Check available memory (minimum 4GB)
    available_memory=$(free -k | awk '/^Mem:/{print $2}')
    min_memory=$((4 * 1024 * 1024)) # 4GB in KB
    
    if [[ $available_memory -lt $min_memory ]]; then
        warn "Less than 4GB RAM available. System may run slowly."
    fi
    
    log "System requirements check passed ✅"
}

# Create project directory structure
create_structure() {
    log "Creating project directory structure..."
    
    # Create main directories
    mkdir -p nginx/{conf.d,ssl}
    mkdir -p postgres/{init,config}
    mkdir -p redis
    mkdir -p backend/{models,api,services,utils}
    mkdir -p dashboard/{public,src/{components,pages,services,utils}}
    mkdir -p firmware/{templates,devices,staging}
    mkdir -p scripts
    mkdir -p logs/{nginx,backend,system}
    mkdir -p docs
    mkdir -p tests/{unit,integration,load}
    
    # Create device firmware directories (sample)
    mkdir -p firmware/devices/{doorlock_otista_001,doorlock_kemayoran_001}
    
    log "Directory structure created ✅"
}

# Set file permissions
set_permissions() {
    log "Setting file permissions..."
    
    # Make scripts executable
    find scripts/ -name "*.sh" -exec chmod +x {} \; 2>/dev/null || true
    
    # Set proper permissions for logs
    chmod -R 755 logs/
    
    # Set proper permissions for firmware storage
    chmod -R 755 firmware/
    
    # Set proper permissions for SSL directory
    chmod -R 700 nginx/ssl/ 2>/dev/null || true
    
    log "File permissions set ✅"
}

# Generate SSL certificates (self-signed for development)
generate_ssl() {
    log "Generating SSL certificates for development..."
    
    if [[ ! -f nginx/ssl/cert.pem ]] || [[ ! -f nginx/ssl/key.pem ]]; then
        openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
            -keyout nginx/ssl/key.pem \
            -out nginx/ssl/cert.pem \
            -subj "/C=ID/ST=Jakarta/L=Jakarta/O=DoorlockSystem/CN=localhost" \
            2>/dev/null || warn "Failed to generate SSL certificates. Manual setup required."
        
        log "SSL certificates generated ✅"
    else
        log "SSL certificates already exist ✅"
    fi
}

# Create default configuration files
create_configs() {
    log "Creating default configuration files..."
    
    # Create Redis config if not exists
    if [[ ! -f redis/redis.conf ]]; then
        cat > redis/redis.conf << 'EOF'
# Redis Configuration for Doorlock System
bind 0.0.0.0
port 6379
timeout 300
keepalive 300
maxmemory 256mb
maxmemory-policy allkeys-lru
save 900 1
save 300 10
save 60 10000
EOF
        log "Redis configuration created ✅"
    fi
    
    # Create nginx default config placeholder
    if [[ ! -f nginx/conf.d/default.conf ]]; then
        cat > nginx/conf.d/default.conf << 'EOF'
# Nginx configuration will be created in Step 1.4
# This is a placeholder file
EOF
        log "Nginx configuration placeholder created ✅"
    fi
}

# Validate environment variables
validate_env() {
    log "Validating environment variables..."
    
    if [[ ! -f .env ]]; then
        error ".env file not found. Please create .env file first."
    fi
    
    # Source environment variables
    source .env
    
    # Check required variables
    required_vars=("POSTGRES_DB" "POSTGRES_USER" "POSTGRES_PASSWORD" "API_KEY")
    
    for var in "${required_vars[@]}"; do
        if [[ -z "${!var}" ]]; then
            error "Required environment variable $var is not set in .env file"
        fi
    done
    
    log "Environment variables validated ✅"
}

# Initialize Docker network
setup_network() {
    log "Setting up Docker network..."
    
    # Check if network already exists
    if docker network ls | grep -q "doorlock-network"; then
        log "Docker network 'doorlock-network' already exists ✅"
    else
        docker network create doorlock-network --driver bridge --subnet=172.20.0.0/16
        log "Docker network 'doorlock-network' created ✅"
    fi
}

# Pull Docker images
pull_images() {
    log "Pulling Docker images..."
    
    # Pull base images
    docker pull postgres:15
    docker pull redis:7-alpine
    docker pull nginx:alpine
    
    log "Docker images pulled ✅"
}

# Create initial docker-compose test
test_compose() {
    log "Testing Docker Compose configuration..."
    
    # Validate compose file
    if docker-compose config > /dev/null 2>&1; then
        log "Docker Compose configuration is valid ✅"
    else
        error "Docker Compose configuration is invalid. Please check docker-compose.yml"
    fi
}

# Create health check script
create_healthcheck() {
    log "Creating health check script..."
    
    cat > scripts/healthcheck.sh << 'EOF'
#!/bin/bash

# Doorlock System Health Check
echo "=== DOORLOCK SYSTEM HEALTH CHECK ==="

# Check container status
echo "Container Status:"
docker-compose ps

echo ""
echo "Network Status:"
docker network inspect doorlock-network --format "{{.Name}}: {{.Driver}}"

echo ""
echo "Volume Status:"
docker volume ls | grep doorlock

echo ""
echo "System Resources:"
echo "Memory Usage: $(free -h | awk '/^Mem:/ {print $3 "/" $2}')"
echo "Disk Usage: $(df -h . | tail -1 | awk '{print $3 "/" $2 " (" $5 ")"}')"

echo ""
echo "=== END HEALTH CHECK ==="
EOF

    chmod +x scripts/healthcheck.sh
    log "Health check script created ✅"
}

# Main setup function
main() {
    echo -e "${BLUE}"
    echo "========================================"
    echo "  DOORLOCK IoT SYSTEM - SETUP"
    echo "========================================"
    echo -e "${NC}"
    
    check_root
    check_requirements
    create_structure
    set_permissions
    generate_ssl
    create_configs
    validate_env
    setup_network
    pull_images
    test_compose
    create_healthcheck
    
    echo ""
    log "🎉 Setup completed successfully!"
    echo ""
    echo -e "${BLUE}Next Steps:${NC}"
    echo "1. Review configuration files in each service directory"
    echo "2. Customize .env file for your environment"
    echo "3. Run: ${GREEN}docker-compose up -d${NC}"
    echo "4. Check system health: ${GREEN}./scripts/healthcheck.sh${NC}"
    echo ""
    echo -e "${YELLOW}Note: This setup creates development SSL certificates.${NC}"
    echo -e "${YELLOW}For production, replace with proper SSL certificates.${NC}"
}

# Run main function
main "$@"
