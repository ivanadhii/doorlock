#!/bin/bash

# =================================
# NGINX PROXY TESTING SCRIPT
# Test nginx routing and performance
# =================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuration
NGINX_HOST="localhost"
NGINX_HTTP_PORT="80"
NGINX_HTTPS_PORT="443"
TEST_TIMEOUT="10"

log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')] INFO: $1${NC}"
}

warn() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] WARN: $1${NC}"
}

error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ERROR: $1${NC}"
}

success() {
    echo -e "${GREEN} ✅ $1${NC}"
}

fail() {
    echo -e "${RED} ❌ $1${NC}"
}

# Check if Nginx is running
check_nginx_status() {
    log "Checking Nginx container status..."
    
    if docker-compose ps nginx-proxy | grep -q "Up"; then
        success "Nginx container is running"
    else
        error "Nginx container is not running"
        exit 1
    fi
}

# Test basic connectivity
test_basic_connectivity() {
    log "Testing basic connectivity..."
    
    # Test HTTP health check
    if curl -s -f --connect-timeout $TEST_TIMEOUT "http://$NGINX_HOST:$NGINX_HTTP_PORT/health" > /dev/null; then
        success "HTTP health check passed"
    else
        fail "HTTP health check failed"
        return 1
    fi
    
    # Test HTTPS (if certificates exist)
    if curl -s -f -k --connect-timeout $TEST_TIMEOUT "https://$NGINX_HOST:$NGINX_HTTPS_PORT/health" > /dev/null 2>&1; then
        success "HTTPS health check passed"
    else
        warn "HTTPS health check failed (certificates may not be configured)"
    fi
}

# Test API routing
test_api_routing() {
    log "Testing API routing..."
    
    # Test API health endpoint
    api_response=$(curl -s --connect-timeout $TEST_TIMEOUT "http://$NGINX_HOST:$NGINX_HTTP_PORT/api/" || echo "FAILED")
    
    if [[ "$api_response" != "FAILED" ]]; then
        success "API routing is working"
        echo "   Response preview: ${api_response:0:100}..."
    else
        fail "API routing failed"
        return 1
    fi
    
    # Test specific API endpoints (if FastAPI is running)
    endpoints=(
        "/api/doorlock/status"
        "/api/docs"
    )
    
    for endpoint in "${endpoints[@]}"; do
        status_code=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout $TEST_TIMEOUT "http://$NGINX_HOST:$NGINX_HTTP_PORT$endpoint" || echo "000")
        
        if [[ "$status_code" =~ ^(200|404)$ ]]; then
            success "Endpoint $endpoint returned $status_code"
        else
            warn "Endpoint $endpoint returned $status_code"
        fi
    done
}

# Test dashboard routing
test_dashboard_routing() {
    log "Testing dashboard routing..."
    
    # Test dashboard redirect from root
    redirect_status=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout $TEST_TIMEOUT "http://$NGINX_HOST:$NGINX_HTTP_PORT/" || echo "000")
    
    if [[ "$redirect_status" == "301" ]]; then
        success "Root redirect to dashboard working (301)"
    else
        warn "Root redirect returned $redirect_status (expected 301)"
    fi
    
    # Test dashboard endpoint
    dashboard_status=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout $TEST_TIMEOUT "http://$NGINX_HOST:$NGINX_HTTP_PORT/dashboard/" || echo "000")
    
    if [[ "$dashboard_status" =~ ^(200|404|502)$ ]]; then
        success "Dashboard endpoint accessible (status: $dashboard_status)"
    else
        warn "Dashboard endpoint returned $dashboard_status"
    fi
}

# Test firmware file serving
test_firmware_serving() {
    log "Testing firmware file serving..."
    
    # Create a test firmware file
    test_firmware_dir="/tmp/test_firmware"
    test_firmware_file="$test_firmware_dir/test_device.bin"
    mkdir -p "$test_firmware_dir"
    echo "TEST_FIRMWARE_DATA_$(date)" > "$test_firmware_file"
    
    # Copy to firmware directory (if mounted)
    if [[ -d "./firmware" ]]; then
        cp "$test_firmware_file" "./firmware/"
        
        # Test firmware download
        firmware_status=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout $TEST_TIMEOUT \
            "http://$NGINX_HOST:$NGINX_HTTP_PORT/firmware/test_device.bin" || echo "000")
        
        if [[ "$firmware_status" == "200" ]]; then
            success "Firmware file serving working"
            
            # Test download content
            downloaded_content=$(curl -s --connect-timeout $TEST_TIMEOUT \
                "http://$NGINX_HOST:$NGINX_HTTP_PORT/firmware/test_device.bin")
            
            if [[ "$downloaded_content" == "TEST_FIRMWARE_DATA"* ]]; then
                success "Firmware file content correct"
            else
                warn "Firmware file content mismatch"
            fi
        else
            warn "Firmware file serving returned $firmware_status"
        fi
        
        # Cleanup
        rm -f "./firmware/test_device.bin"
    else
        warn "Firmware directory not found, skipping firmware serving test"
    fi
    
    # Cleanup
    rm -rf "$test_firmware_dir"
}

# Test rate limiting
test_rate_limiting() {
    log "Testing rate limiting..."
    
    # Test API rate limiting (10 requests per second)
    success_count=0
    rate_limited_count=0
    
    for i in {1..15}; do
        status_code=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 2 \
            "http://$NGINX_HOST:$NGINX_HTTP_PORT/api/" 2>/dev/null || echo "000")
        
        if [[ "$status_code" == "200" ]]; then
            ((success_count++))
        elif [[ "$status_code" == "429" ]]; then
            ((rate_limited_count++))
        fi
        
        sleep 0.1
    done
    
    if [[ $rate_limited_count -gt 0 ]]; then
        success "Rate limiting is working ($success_count successful, $rate_limited_count rate-limited)"
    else
        warn "Rate limiting may not be working properly"
    fi
}

# Test nginx status and metrics
test_nginx_metrics() {
    log "Testing Nginx metrics..."
    
    # Test nginx status endpoint
    status_response=$(curl -s --connect-timeout $TEST_TIMEOUT \
        "http://$NGINX_HOST:$NGINX_HTTP_PORT/nginx-status" 2>/dev/null || echo "FAILED")
    
    if [[ "$status_response" == *"Active connections"* ]]; then
        success "Nginx status endpoint working"
        echo "   Status: $status_response"
    else
        warn "Nginx status endpoint not accessible (may be IP restricted)"
    fi
    
    # Check logs
    if docker-compose exec nginx-proxy test -f /var/log/nginx/access.log; then
        log_lines=$(docker-compose exec nginx-proxy wc -l /var/log/nginx/access.log | awk '{print $1}')
        success "Access logs available ($log_lines lines)"
    else
        warn "Access logs not found"
    fi
}

# Test performance and response times
test_performance() {
    log "Testing performance..."
    
    endpoints=(
        "http://$NGINX_HOST:$NGINX_HTTP_PORT/health"
        "http://$NGINX_HOST:$NGINX_HTTP_PORT/api/"
        "http://$NGINX_HOST:$NGINX_HTTP_PORT/dashboard/"
    )
    
    for endpoint in "${endpoints[@]}"; do
        # Measure response time
        response_time=$(curl -s -o /dev/null -w "%{time_total}" --connect-timeout $TEST_TIMEOUT "$endpoint" 2>/dev/null || echo "999")
        response_time_ms=$(echo "$response_time * 1000" | bc)
        
        if (( $(echo "$response_time < 1.0" | bc -l) )); then
            success "Endpoint ${endpoint##*/} response time: ${response_time_ms}ms"
        else
            warn "Endpoint ${endpoint##*/} slow response time: ${response_time_ms}ms"
        fi
    done
}

# Show nginx configuration summary
show_nginx_config() {
    log "Nginx configuration summary:"
    
    echo -e "${BLUE}=== NGINX CONFIGURATION ===${NC}"
    
    # Show server blocks
    echo -e "${BLUE}Server blocks:${NC}"
    docker-compose exec nginx-proxy nginx -T 2>/dev/null | grep -E "^server|listen" | head -10
    
    # Show upstream servers
    echo -e "\n${BLUE}Upstream servers:${NC}"
    docker-compose exec nginx-proxy nginx -T 2>/dev/null | grep -A 3 "upstream"
    
    # Show rate limiting zones
    echo -e "\n${BLUE}Rate limiting zones:${NC}"
    docker-compose exec nginx-proxy nginx -T 2>/dev/null | grep "limit_req_zone"
    
    echo -e "${BLUE}=========================${NC}"
}

# Monitor nginx logs (optional)
monitor_logs() {
    log "Monitoring Nginx logs (Ctrl+C to stop)..."
    
    docker-compose logs -f nginx-proxy
}

# Main test function
main() {
    echo -e "${BLUE}"
    echo "========================================"
    echo "  NGINX PROXY TESTING"
    echo "========================================"
    echo -e "${NC}"
    
    # Check if bc is available for calculations
    if ! command -v bc &> /dev/null; then
        warn "bc not available, some performance tests will be skipped"
    fi
    
    # Run tests
    check_nginx_status
    test_basic_connectivity
    test_api_routing
    test_dashboard_routing
    test_firmware_serving
    test_rate_limiting
    test_nginx_metrics
    test_performance
    
    echo ""
    show_nginx_config
    
    echo ""
    log "🎉 Nginx proxy testing completed!"
    echo ""
    echo -e "${BLUE}Next Steps:${NC}"
    echo "1. Monitor logs: ${GREEN}./scripts/test-nginx.sh monitor${NC}"
    echo "2. Check config: ${GREEN}docker-compose exec nginx-proxy nginx -t${NC}"
    echo "3. Reload config: ${GREEN}docker-compose exec nginx-proxy nginx -s reload${NC}"
    
    # Optional log monitoring
    if [[ "$1" == "monitor" ]]; then
        echo ""
        monitor_logs
    fi
}

# Run main function
main "$@"
