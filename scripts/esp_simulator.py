#!/usr/bin/env python3
"""
ESP8266 Simulator for Doorlock System Testing
Sends real production JSON structure with dummy data
"""

import requests
import json
import time
import random
from datetime import datetime, timedelta

# Server Configuration
SERVER_URL = "http://localhost:8000"
API_KEY = "kentutbau123"

# Device Configuration (Production Structure)
DEVICES = [
    {
        "device_id": "doorlock_otista_001",
        "location": "otista",
        "device_name": "Otista Main Door"
    },
    {
        "device_id": "doorlock_otista_002", 
        "location": "otista",
        "device_name": "Otista Side Door"
    },
    {
        "device_id": "doorlock_kemayoran_001",
        "location": "kemayoran", 
        "device_name": "Kemayoran Main Door"
    },
    {
        "device_id": "doorlock_kemayoran_002",
        "location": "kemayoran",
        "device_name": "Kemayoran Staff Door"
    }
]

# Sample Card UIDs (Production Format)
SAMPLE_CARDS = [
    "04A1B2C3D4E5F6",  # John Doe
    "04B1C2D3E4F5A6",  # Jane Smith
    "04C1D2E3F4A5B6",  # Mike Johnson
    "04D1E2F3A4B5C6",  # Sarah Wilson
    "E004123456",       # Invalid card
    "04UNKNOWN001",     # Unknown card
]

def generate_session_id():
    """Generate production format session ID: YYYYMMDD_HHMM_XXX"""
    now = datetime.now()
    return f"{now.strftime('%Y%m%d_%H%M')}_{random.randint(1, 999):03d}"

def generate_access_logs(device_id, count=5):
    """Generate realistic access logs for 8-hour period"""
    logs = []
    base_time = datetime.now() - timedelta(hours=8)
    
    for i in range(count):
        # Random time within 8-hour period
        log_time = base_time + timedelta(seconds=random.randint(0, 8*3600))
        
        # Random card
        card_uid = random.choice(SAMPLE_CARDS)
        
        # Simulate access pattern (most granted, some denied)
        if card_uid == "E004123456":
            access_granted = False  # Invalid card always denied
        elif card_uid == "04UNKNOWN001":
            access_granted = random.choice([True, False])  # Mixed for unknown
        else:
            access_granted = random.choice([True, True, True, False])  # Mostly granted
        
        logs.append({
            "card_uid": card_uid,
            "access_granted": access_granted,
            "access_type": "rfid",
            "user_name": None,  # ESP doesn't send names (dashboard will provide)
            "timestamp": log_time.strftime("%Y-%m-%dT%H:%M:%SZ")
        })
    
    # Sort by timestamp
    logs.sort(key=lambda x: x["timestamp"])
    return logs

def generate_device_status():
    """Generate realistic device status"""
    return {
        "door_status": random.choice(["locked", "locked", "locked", "unlocked"]),  # Mostly locked
        "rfid_enabled": random.choice([True, True, True, False]),  # Mostly enabled
        "battery_percentage": random.randint(60, 100),
        "uptime_seconds": random.randint(3600, 8*3600),  # 1-8 hours
        "wifi_rssi": random.randint(-70, -40),
        "free_heap": random.randint(20000, 30000)
    }

def create_bulk_upload_payload(device):
    """Create production format bulk upload payload"""
    session_id = generate_session_id()
    now = datetime.now()
    eight_hours_ago = now - timedelta(hours=8)
    
    payload = {
        "doorlock": {
            "device_id": device["device_id"],
            "location": device["location"],
            "sync_session": {
                "session_id": session_id,
                "period": {
                    "from": eight_hours_ago.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "to": now.strftime("%Y-%m-%dT%H:%M:%SZ")
                }
            },
            "current_status": generate_device_status(),
            "access_logs": generate_access_logs(device["device_id"]),
            "spam_detected": random.choice([False, False, False, True]),  # Rarely spam
            "total_access_count": random.randint(50, 200),
            "timestamp": now.strftime("%Y-%m-%dT%H:%M:%SZ")
        }
    }
    
    return payload

def send_bulk_upload(device):
    """Send bulk upload to server"""
    payload = create_bulk_upload_payload(device)
    
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": API_KEY
    }
    
    print(f"\n🚀 Sending bulk upload for {device['device_id']}...")
    print(f"   📍 Location: {device['location']}")
    print(f"   📊 Access logs: {len(payload['doorlock']['access_logs'])}")
    print(f"   🔋 Battery: {payload['doorlock']['current_status']['battery_percentage']}%")
    print(f"   🚪 Door: {payload['doorlock']['current_status']['door_status']}")
    
    try:
        response = requests.post(
            f"{SERVER_URL}/api/doorlock/bulk-upload",
            headers=headers,
            json=payload,
            timeout=10
        )
        
        if response.status_code == 200:
            print(f"   ✅ Success: {response.status_code}")
            
            # Parse server response (commands)
            server_response = response.json()
            commands = server_response.get("doorlock", {}).get("commands", [])
            
            if commands:
                print(f"   📨 Received {len(commands)} commands:")
                for cmd in commands:
                    print(f"      - {cmd['type']}: {cmd['action']}")
                
                # Simulate command acknowledgment
                simulate_command_ack(device, commands)
            else:
                print("   📝 No commands received")
                
        else:
            print(f"   ❌ Error: {response.status_code}")
            print(f"      Response: {response.text[:200]}")
            
    except requests.exceptions.RequestException as e:
        print(f"   ❌ Request failed: {e}")

def simulate_command_ack(device, commands):
    """Simulate command acknowledgment"""
    if not commands:
        return
        
    print(f"\n🔄 Processing commands for {device['device_id']}...")
    
    command_responses = []
    for cmd in commands:
        # Simulate command execution delay
        time.sleep(1)
        
        # Simulate command success/failure (mostly success)
        status = random.choice(["success", "success", "success", "failed"])
        
        command_responses.append({
            "command_id": cmd["command_id"],
            "status": status,
            "executed_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
        })
        
        print(f"   ⚡ Command {cmd['command_id']}: {status}")
    
    # Send acknowledgment
    ack_payload = {
        "doorlock": {
            "device_id": device["device_id"],
            "command_responses": command_responses,
            "timestamp": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
        }
    }
    
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": API_KEY
    }
    
    try:
        response = requests.post(
            f"{SERVER_URL}/api/doorlock/command-ack",
            headers=headers,
            json=ack_payload,
            timeout=10
        )
        
        if response.status_code == 200:
            print(f"   ✅ Command ACK sent successfully")
        else:
            print(f"   ❌ Command ACK failed: {response.status_code}")
            
    except requests.exceptions.RequestException as e:
        print(f"   ❌ Command ACK request failed: {e}")

def test_server_endpoints():
    """Test various server endpoints"""
    headers = {"X-API-Key": API_KEY}
    
    print("\n🧪 Testing Server Endpoints...")
    
    endpoints_to_test = [
        ("GET", "/health", "Health check"),
        ("GET", "/api/doorlock/status", "Device status"),
        ("GET", "/api/dashboard/overview", "Dashboard overview"),
        ("GET", "/api/dashboard/recent-activity", "Recent activity"),
    ]
    
    for method, endpoint, description in endpoints_to_test:
        try:
            if method == "GET":
                response = requests.get(f"{SERVER_URL}{endpoint}", headers=headers, timeout=5)
            
            if response.status_code == 200:
                print(f"   ✅ {description}: OK")
                if "recent-activity" in endpoint:
                    data = response.json()
                    activities = data.get("activities", [])
                    print(f"      📊 Found {len(activities)} recent activities")
            else:
                print(f"   ❌ {description}: {response.status_code}")
                
        except Exception as e:
            print(f"   ❌ {description}: {e}")

def send_remote_commands():
    """Send some test remote commands"""
    headers = {"X-API-Key": API_KEY}
    
    print("\n📡 Sending Test Remote Commands...")
    
    # Test unlock timer command
    device_id = DEVICES[0]["device_id"]
    try:
        response = requests.post(
            f"{SERVER_URL}/api/doorlock/command/unlock-timer",
            headers=headers,
            params={"device_id": device_id, "duration_minutes": 30},
            timeout=5
        )
        
        if response.status_code == 200:
            print(f"   ✅ Unlock timer command queued for {device_id}")
        else:
            print(f"   ❌ Unlock timer failed: {response.status_code}")
            
    except Exception as e:
        print(f"   ❌ Unlock timer request failed: {e}")
    
    # Test RFID control command
    try:
        response = requests.post(
            f"{SERVER_URL}/api/doorlock/command/rfid-control",
            headers=headers,
            params={"device_id": device_id, "action": "disable"},
            timeout=5
        )
        
        if response.status_code == 200:
            print(f"   ✅ RFID control command queued for {device_id}")
        else:
            print(f"   ❌ RFID control failed: {response.status_code}")
            
    except Exception as e:
        print(f"   ❌ RFID control request failed: {e}")

def simulate_8_hour_sync():
    """Simulate 8-hour sync cycle for all devices"""
    print("=" * 60)
    print("🏠 ESP8266 DOORLOCK SYSTEM SIMULATOR")
    print("=" * 60)
    print(f"🌐 Server: {SERVER_URL}")
    print(f"🔑 API Key: {API_KEY}")
    print(f"📱 Devices: {len(DEVICES)}")
    print("=" * 60)
    
    # Test server first
    test_server_endpoints()
    
    # Send some remote commands first (to test command queue)
    send_remote_commands()
    
    # Wait a bit then simulate device sync
    print("\n⏰ Waiting 3 seconds before sync...")
    time.sleep(3)
    
    # Simulate sync for each device
    print("\n🔄 Starting 8-hour sync simulation...")
    
    for i, device in enumerate(DEVICES):
        print(f"\n📱 Device {i+1}/{len(DEVICES)}: {device['device_id']}")
        send_bulk_upload(device)
        
        # Small delay between devices (simulate real-world timing)
        if i < len(DEVICES) - 1:
            print("   ⏳ Waiting 2 seconds...")
            time.sleep(2)
    
    print("\n" + "=" * 60)
    print("✅ 8-HOUR SYNC SIMULATION COMPLETED")
    print("=" * 60)
    print("\n💡 What happened:")
    print("   1. ✅ Tested server endpoints")
    print("   2. ✅ Queued remote commands")
    print("   3. ✅ Simulated ESP8266 bulk uploads (8-hour data)")
    print("   4. ✅ Processed command acknowledgments")
    print("   5. ✅ Generated realistic access logs")
    print("\n🎯 Check your database now:")
    print("   - Device status should be updated")
    print("   - Access logs should contain dummy entries")
    print("   - Commands should show execution status")
    print("\n🚀 Ready for dashboard development!")

def continuous_simulation():
    """Run continuous simulation (like real ESP8266 schedule)"""
    print("\n🔄 Starting continuous simulation...")
    print("   (Press Ctrl+C to stop)")
    
    try:
        while True:
            simulate_8_hour_sync()
            print(f"\n⏰ Next sync in 30 seconds... (simulating 8-hour interval)")
            time.sleep(30)  # In real system: 8 hours
            
    except KeyboardInterrupt:
        print("\n\n⏹️ Simulation stopped by user")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "continuous":
        continuous_simulation()
    else:
        simulate_8_hour_sync()