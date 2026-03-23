# api.py - FastAPI application
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from session_manager import SessionManager
from mqtt_client import MQTTClient
from telemetry import TelemetryManager
import state

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)


# Request models
class PreflightRequest(BaseModel):
    start_in: int = Field(..., gt=0, description="Seconds until recording starts")
    nodes: list[str] = Field(default_factory=list, description="Node IDs that must confirm")


# Managers (initialized in lifespan)
session_mgr: SessionManager | None = None
telemetry_mgr: TelemetryManager | None = None
mqtt_client: MQTTClient | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle startup and shutdown."""
    global session_mgr, telemetry_mgr, mqtt_client

    logger.info("Starting up...")

    # Initialize managers
    session_mgr = SessionManager()
    telemetry_mgr = TelemetryManager()
    mqtt_client = MQTTClient()

    # Wire up dependencies
    session_mgr.set_mqtt_client(mqtt_client)
    mqtt_client.set_node_confirmation_callback(session_mgr.on_all_nodes_confirmed)

    # Subscribe to state changes for MQTT broadcast
    session_mgr.subscribe(mqtt_client.publish_status)
    telemetry_mgr.subscribe(mqtt_client.publish_status)

    # Start telemetry collection
    telemetry_mgr.start()

    logger.info("Startup complete")

    yield  # App runs here

    # Shutdown
    logger.info("Shutting down...")
    telemetry_mgr.stop()
    mqtt_client.stop()
    logger.info("Shutdown complete")


app = FastAPI(
    title="Controller API",
    description="Recording session controller with distributed node coordination",
    version="1.0.0",
    lifespan=lifespan
)


@app.get("/state")
def get_state():
    """Get current state including countdown if in preflight."""
    return state.get_snapshot()


@app.post("/preflight")
def start_preflight(request: PreflightRequest):
    """
    Start preflight phase with scheduled recording.
    
    - Generates a new session UUID
    - Broadcasts prepare command to nodes
    - Starts countdown timer
    - Transitions to recording when countdown expires and all nodes confirmed
    """
    success, result = session_mgr.start_preflight(request.start_in, request.nodes)

    if not success:
        raise HTTPException(status_code=400, detail=result)

    return state.get_snapshot()


@app.post("/cancel")
def cancel_preflight():
    """
    Cancel preflight and return to idle.
    
    - Only valid during preflight state
    - Broadcasts abort command to nodes
    """
    success, result = session_mgr.cancel()

    if not success:
        raise HTTPException(status_code=400, detail=result)

    return state.get_snapshot()


@app.post("/stop")
def stop_recording():
    """
    Stop recording and transition to finishing.
    
    - Only valid during recording state
    - Broadcasts stop command to nodes
    - Performs cleanup, then transitions to idle
    """
    success, result = session_mgr.stop_recording()

    if not success:
        raise HTTPException(status_code=400, detail=result)

    return state.get_snapshot()


@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {
        "status": "ok",
        "mqtt_connected": mqtt_client.connected if mqtt_client else False
    }
