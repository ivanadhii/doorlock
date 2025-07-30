#!/bin/bash

# =================================
# SSL CERTIFICATE SETUP SCRIPT
# Generate or install SSL certificates for Nginx
# =================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuration
SSL_DIR="./nginx/ssl"
DOMAIN_NAME="${DOMAIN_NAME:-doorlock-backend.meltedcloud.cloud}"
SSL_EMAIL="${SSL_EMAIL:-admin@meltedcloud.cloud}"

log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')] INFO: $1${NC}"
}

warn() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] WARN: $1${NC}"
}

error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ERROR: $1${NC}"
}

# Create SSL directory
create_ssl_directory() {
    log "Creating SSL directory..."
    mkdir -p "$SSL_DIR"
    chmod 700 "$SSL_DIR"
}

# Generate self-signed certificates for development
generate_self_signed() {
    log "Generating self-signed certificates for development..."
    
    # Generate private key
    openssl genrsa -out "$SSL_DIR/key.pem" 2048
    
    # Generate certificate
    openssl req -new -x509 -key "$SSL_DIR/key.pem" -out "$SSL_DIR/cert.pem" -days 365 \
        -subj "/C=ID/ST=Jakarta/L=Jakarta/O=DoorlockSystem/CN=$DOMAIN_NAME" \
        -addext "subjectAltName=DNS:$DOMAIN_NAME,DNS:localhost,IP:127.0.0.1"
    
    # Set proper permissions
    chmod 600 "$SSL_DIR/key.pem"
    chmod 644 "$SSL_DIR/cert.pem"
    
    log "Self-signed certificates generated ✅"
    echo "   Certificate: $SSL_DIR/cert.pem"
    echo "   Private key: $SSL_DIR/key.pem"
    echo "   Valid for: 365 days"
}

# Setup Let's Encrypt certificates (production)
setup_letsencrypt() {
    log "Setting up Let's Encrypt certificates..."
    
    # Check if certbot is available
    if ! command -v certbot &> /dev/null; then
        error "Certbot not found. Please install certbot first:"
        echo "   Ubuntu/Debian: sudo apt install certbot"
        echo "   CentOS/RHEL: sudo yum install certbot"
        exit 1
    fi
    
    # Stop nginx temporarily
    log "Stopping nginx for certificate generation..."
    docker-compose stop nginx-proxy || true
    
    # Generate certificate
    log "Requesting certificate from Let's Encrypt..."
    certbot certonly --standalone \
        --email "$SSL_EMAIL" \
        --agree-tos \
        --no-eff-email \
        -d "$DOMAIN_NAME"
    
    # Copy certificates to nginx directory
    log "Copying certificates to nginx directory..."
    cp "/etc/letsencrypt/live/$DOMAIN_NAME/fullchain.pem" "$SSL_DIR/cert.pem"
    cp "/etc/letsencrypt/live/$DOMAIN_NAME/privkey.pem" "$SSL_DIR/key.pem"
    
    # Set proper permissions
    chmod 600 "$SSL_DIR/key.pem"
    chmod 644 "$SSL_DIR/cert.pem"
    
    # Restart nginx
    log "Starting nginx with new certificates..."
    docker-compose start nginx-proxy
    
    log "Let's Encrypt certificates installed ✅"
}

# Install custom certificates
install_custom_certs() {
    local cert_file="$1"
    local key_file="$2"
    
    if [[ -z "$cert_file" || -z "$key_file" ]]; then
        error "Usage: install_custom_certs <cert_file> <key_file>"
        exit 1
    fi
    
    if [[ ! -f "$cert_file" || ! -f "$key_file" ]]; then
        error "Certificate or key file not found"
        exit 1
    fi
    
    log "Installing custom certificates..."
    
    # Copy certificates
    cp "$cert_file" "$SSL_DIR/cert.pem"
    cp "$key_file" "$SSL_DIR/key.pem"
    
    # Set proper permissions
    chmod 600 "$SSL_DIR/key.pem"
    chmod 644 "$SSL_DIR/cert.pem"
    
    log "Custom certificates installed ✅"
}

# Verify certificates
verify_certificates() {
    log "Verifying SSL certificates..."
    
    if [[ ! -f "$SSL_DIR/cert.pem" || ! -f "$SSL_DIR/key.pem" ]]; then
        error "SSL certificates not found"
        return 1
    fi
    
    # Check certificate validity
    cert_info=$(openssl x509 -in "$SSL_DIR/cert.pem" -text -noout)
    
    # Extract information
    subject=$(echo "$cert_info" | grep "Subject:" | head -1)
    issuer=$(echo "$cert_info" | grep "Issuer:" | head -1)
    valid_from=$(echo "$cert_info" | grep "Not Before:" | head -1)
    valid_until=$(echo "$cert_info" | grep "Not After:" | head -1)
    
    echo -e "${BLUE}Certificate Information:${NC}"
    echo "   $subject"
    echo "   $issuer"
    echo "   $valid_from"
    echo "   $valid_until"
    
    # Check if certificate matches private key
    cert_modulus=$(openssl x509 -noout -modulus -in "$SSL_DIR/cert.pem" | openssl md5)
    key_modulus=$(openssl rsa -noout -modulus -in "$SSL_DIR/key.pem" | openssl md5)
    
    if [[ "$cert_modulus" == "$key_modulus" ]]; then
        log "Certificate and private key match ✅"
    else
        error "Certificate and private key do not match ❌"
        return 1
    fi
    
    # Check certificate expiration
    if openssl x509 -checkend 86400 -noout -in "$SSL_DIR/cert.pem" > /dev/null; then
        log "Certificate is valid for at least 24 hours ✅"
    else
        warn "Certificate expires within 24 hours ⚠️"
    fi
}

# Test SSL connection
test_ssl_connection() {
    log "Testing SSL connection..."
    
    # Wait for nginx to start
    sleep 5
    
    # Test HTTPS connection
    if curl -k -s --connect-timeout 10 "https://localhost/health" > /dev/null 2>&1; then
        log "HTTPS connection test passed ✅"
    else
        warn "HTTPS connection test failed"
        return 1
    fi
    
    # Test SSL certificate
    ssl_info=$(echo | openssl s_client -connect localhost:443 -servername "$DOMAIN_NAME" 2>/dev/null | openssl x509 -noout -text)
    
    if [[ -n "$ssl_info" ]]; then
        log "SSL certificate is being served correctly ✅"
    else
        warn "SSL certificate not being served properly"
    fi
}

# Setup certificate renewal (for Let's Encrypt)
setup_certificate_renewal() {
    log "Setting up certificate renewal..."
    
    # Create renewal script
    cat > "$SSL_DIR/renew-certs.sh" << 'EOF'
#!/bin/bash
# Certificate renewal script for Let's Encrypt

DOMAIN_NAME="${DOMAIN_NAME:-doorlock-backend.meltedcloud.cloud}"
SSL_DIR="./nginx/ssl"

# Renew certificate
certbot renew --quiet

# Copy renewed certificates
if [[ -f "/etc/letsencrypt/live/$DOMAIN_NAME/fullchain.pem" ]]; then
    cp "/etc/letsencrypt/live/$DOMAIN_NAME/fullchain.pem" "$SSL_DIR/cert.pem"
    cp "/etc/letsencrypt/live/$DOMAIN_NAME/privkey.pem" "$SSL_DIR/key.pem"
    
    # Reload nginx
    docker-compose exec nginx-proxy nginx -s reload
    
    echo "Certificates renewed and nginx reloaded"
fi
EOF
    
    chmod +x "$SSL_DIR/renew-certs.sh"
    
    # Add to crontab (optional)
    echo ""
    log "Certificate renewal script created: $SSL_DIR/renew-certs.sh"
    echo ""
    echo -e "${YELLOW}To setup automatic renewal, add this to your crontab:${NC}"
    echo "   0 3 * * * $(pwd)/$SSL_DIR/renew-certs.sh >> /var/log/cert-renewal.log 2>&1"
    echo ""
    echo -e "${YELLOW}Run: crontab -e${NC}"
}

# Show SSL status
show_ssl_status() {
    log "SSL Status Summary:"
    
    echo -e "${BLUE}=== SSL CERTIFICATE STATUS ===${NC}"
    
    if [[ -f "$SSL_DIR/cert.pem" && -f "$SSL_DIR/key.pem" ]]; then
        echo -e "${GREEN}✅ Certificates found${NC}"
        
        # Show certificate details
        cert_subject=$(openssl x509 -noout -subject -in "$SSL_DIR/cert.pem" | sed 's/subject=//')
        cert_issuer=$(openssl x509 -noout -issuer -in "$SSL_DIR/cert.pem" | sed 's/issuer=//')
        cert_expires=$(openssl x509 -noout -enddate -in "$SSL_DIR/cert.pem" | sed 's/notAfter=//')
        
        echo "   Subject: $cert_subject"
        echo "   Issuer: $cert_issuer"
        echo "   Expires: $cert_expires"
        
        # Check days until expiration
        expiry_date=$(openssl x509 -noout -enddate -in "$SSL_DIR/cert.pem" | cut -d= -f2)
        expiry_epoch=$(date -d "$expiry_date" +%s)
        current_epoch=$(date +%s)
        days_left=$(( (expiry_epoch - current_epoch) / 86400 ))
        
        if [[ $days_left -gt 30 ]]; then
            echo -e "   ${GREEN}Days until expiry: $days_left${NC}"
        elif [[ $days_left -gt 7 ]]; then
            echo -e "   ${YELLOW}Days until expiry: $days_left${NC}"
        else
            echo -e "   ${RED}Days until expiry: $days_left${NC}"
        fi
        
    else
        echo -e "${RED}❌ Certificates not found${NC}"
    fi
    
    echo -e "${BLUE}===========================${NC}"
}

# Main function
main() {
    echo -e "${BLUE}"
    echo "========================================"
    echo "  SSL CERTIFICATE SETUP"
    echo "========================================"
    echo -e "${NC}"
    
    create_ssl_directory
    
    case "${1:-self-signed}" in
        "self-signed")
            generate_self_signed
            ;;
        "letsencrypt")
            setup_letsencrypt
            setup_certificate_renewal
            ;;
        "custom")
            install_custom_certs "$2" "$3"
            ;;
        "verify")
            verify_certificates
            test_ssl_connection
            ;;
        "status")
            show_ssl_status
            exit 0
            ;;
        "renew")
            if [[ -f "$SSL_DIR/renew-certs.sh" ]]; then
                "$SSL_DIR/renew-certs.sh"
            else
                error "Renewal script not found. Run with 'letsencrypt' option first."
                exit 1
            fi
            ;;
        *)
            echo "Usage: $0 {self-signed|letsencrypt|custom <cert> <key>|verify|status|renew}"
            echo ""
            echo "Options:"
            echo "  self-signed    Generate self-signed certificates (development)"
            echo "  letsencrypt    Setup Let's Encrypt certificates (production)"
            echo "  custom         Install custom certificate files"
            echo "  verify         Verify existing certificates"
            echo "  status         Show certificate status"
            echo "  renew          Renew Let's Encrypt certificates"
            exit 1
            ;;
    esac
    
    # Verify certificates after setup
    if [[ "$1" != "status" ]]; then
        echo ""
        verify_certificates
        show_ssl_status
        
        # Restart nginx to use new certificates
        if docker-compose ps nginx-proxy | grep -q "Up"; then
            log "Reloading nginx configuration..."
            docker-compose exec nginx-proxy nginx -s reload
        fi
    fi
    
    echo ""
    log "🎉 SSL setup completed!"
    echo ""
    echo -e "${BLUE}Next Steps:${NC}"
    echo "1. Test HTTPS: ${GREEN}curl -k https://localhost/health${NC}"
    echo "2. Check logs: ${GREEN}docker-compose logs nginx-proxy${NC}"
    echo "3. Monitor: ${GREEN}./scripts/test-nginx.sh${NC}"
}

# Run main function
main "$@"
