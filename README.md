# ctlr-core

Distributed recording session controller with MQTT-based node coordination.

## Overview

This controller manages recording sessions across multiple nodes. It coordinates:
- Preflight hardware checks
- Scheduled recording start times
- Node confirmation before recording
- Graceful session cleanup

## State Machine

```
idle → preflight → recording → finishing → idle
         ↓
       (cancel/timeout)
         ↓
        idle
```

### States

| State | Description |
|-------|-------------|
| `idle` | No active session. Ready to start preflight. |
| `preflight` | Preparing for recording. Waiting for node confirmations and countdown. |
| `recording` | Active recording session. |
| `finishing` | Cleaning up after recording. Flushing buffers, closing files. |

## API Endpoints

### GET /state
Returns current state with telemetry and countdown (if in preflight).

```json
{
  "state": "preflight",
  "uuid": "550e8400-e29b-41d4-a716-446655440000",
  "countdown": 8,
  "expected_nodes": ["node1", "node2"],
  "confirmed_nodes": ["node1"],
  "all_confirmed": false,
  "cpu": 12.5,
  "memory": 45.2,
  "storage": 67.8
}
```

### POST /preflight
Start preflight with scheduled recording.

**Request:**
```json
{
  "start_in": 10,
  "nodes": ["node1", "node2"]
}
```

**Response:** Current state snapshot

### POST /cancel
Cancel preflight and return to idle. Only valid during `preflight` state.

### POST /stop
Stop recording and transition to finishing. Only valid during `recording` state.

### GET /health
Health check endpoint.

```json
{
  "status": "ok",
  "mqtt_connected": true
}
```

## MQTT Topics

### Published by Controller

| Topic | Description |
|-------|-------------|
| `ctlr/status` | Current state (published on every state change and telemetry update) |
| `ctlr/command` | Commands to nodes: `prepare`, `start`, `stop`, `abort` |

### Subscribed by Controller

| Topic | Description |
|-------|-------------|
| `ctlr/node/+/ready` | Node ready confirmations |

### Command Payloads

**prepare** (sent at preflight start):
```json
{
  "action": "prepare",
  "uuid": "...",
  "start_at": "2026-03-23T18:10:00",
  "nodes": ["node1", "node2"]
}
```

**start** (sent when countdown reaches 0):
```json
{
  "action": "start",
  "uuid": "..."
}
```

**stop** (sent when recording stopped):
```json
{
  "action": "stop",
  "uuid": "..."
}
```

**abort** (sent on cancel or timeout):
```json
{
  "action": "abort",
  "uuid": "...",
  "reason": "User cancelled"
}
```

### Node Ready Payload

Nodes publish to `ctlr/node/{node_id}/ready`:
```json
{
  "node_id": "node1",
  "ready": true
}
```

Or on error:
```json
{
  "node_id": "node1",
  "ready": false,
  "error": "Hardware check failed"
}
```

## Configuration

Configuration via environment variables or `.env` file:

| Variable | Default | Description |
|----------|---------|-------------|
| `MQTT_BROKER` | localhost | MQTT broker hostname |
| `MQTT_PORT` | 1883 | MQTT broker port |
| `MQTT_TOPIC_PREFIX` | ctlr | Prefix for all MQTT topics |
| `API_HOST` | 0.0.0.0 | API server bind address |
| `API_PORT` | 8000 | API server port |
| `TELEMETRY_INTERVAL` | 2 | Seconds between telemetry updates |
| `PREFLIGHT_TIMEOUT` | 30 | Max seconds to wait for node confirmations |

## Installation

```bash
cd server
python -m venv .venv
source .venv/bin/activate
pip install fastapi uvicorn paho-mqtt psutil python-dotenv pydantic-settings
```

## Running

```bash
cd server
source ../.venv/bin/activate
python main.py
```

## Development

### Project Structure

```
ctlr-core/
├── README.md
├── .venv/
└── server/
    ├── .env              # Configuration
    ├── config.py         # Settings loader
    ├── state.py          # Thread-safe shared state
    ├── session_manager.py # State machine & coordination
    ├── mqtt_client.py    # MQTT pub/sub
    ├── telemetry.py      # System metrics collection
    ├── api.py            # FastAPI endpoints
    └── main.py           # Entry point
```

### Testing Locally

```bash
# Terminal 1: Monitor MQTT
mosquitto_sub -t "ctlr/#" -v

# Terminal 2: Start server
python main.py

# Terminal 3: Test API
curl http://localhost:8000/state
curl -X POST http://localhost:8000/preflight -H "Content-Type: application/json" -d '{"start_in": 10, "nodes": []}'

# Simulate node confirmation
mosquitto_pub -t "ctlr/node/node1/ready" -m '{"node_id": "node1", "ready": true}'
```
