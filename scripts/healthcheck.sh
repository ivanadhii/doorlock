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
