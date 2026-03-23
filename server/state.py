# state.py - Thread-safe shared application state
import threading
from datetime import datetime

_lock = threading.Lock()

# Valid states
VALID_STATES = {"idle", "preflight", "recording", "finishing"}

# Session info
current_state = "idle"
session_uuid = None

# Preflight coordination
start_at: datetime | None = None
expected_nodes: set = set()
confirmed_nodes: set = set()
preflight_deadline: datetime | None = None

# Telemetry
cpu_percent = 0.0
memory_percent = 0.0
storage_percent = 0.0


def get_snapshot() -> dict:
    """Get a consistent snapshot of all state at once."""
    with _lock:
        snapshot = {
            "state": current_state,
            "uuid": session_uuid,
            "cpu": cpu_percent,
            "memory": memory_percent,
            "storage": storage_percent
        }
        # Add preflight info if in preflight state
        if current_state == "preflight" and start_at is not None:
            now = datetime.now()
            countdown = max(0, int((start_at - now).total_seconds()))
            snapshot["countdown"] = countdown
            snapshot["expected_nodes"] = list(expected_nodes)
            snapshot["confirmed_nodes"] = list(confirmed_nodes)
            snapshot["all_confirmed"] = expected_nodes == confirmed_nodes
        return snapshot


def get_current_state() -> str:
    """Thread-safe read of current state."""
    with _lock:
        return current_state


def update_session(new_state: str, new_uuid: str | None = None):
    """Atomically update session state."""
    global current_state, session_uuid
    with _lock:
        current_state = new_state
        if new_uuid is not None:
            session_uuid = new_uuid


def update_telemetry(cpu: float, memory: float, storage: float):
    """Atomically update all telemetry values."""
    global cpu_percent, memory_percent, storage_percent
    with _lock:
        cpu_percent = cpu
        memory_percent = memory
        storage_percent = storage


def setup_preflight(scheduled_start: datetime, nodes: list[str], deadline: datetime):
    """Initialize preflight coordination data."""
    global start_at, expected_nodes, confirmed_nodes, preflight_deadline
    with _lock:
        start_at = scheduled_start
        expected_nodes = set(nodes)
        confirmed_nodes = set()
        preflight_deadline = deadline


def confirm_node(node_id: str) -> bool:
    """
    Mark a node as confirmed.
    Returns True if all expected nodes are now confirmed.
    """
    global confirmed_nodes
    with _lock:
        if node_id in expected_nodes:
            confirmed_nodes.add(node_id)
        return expected_nodes == confirmed_nodes and len(expected_nodes) > 0


def all_nodes_confirmed() -> bool:
    """Check if all expected nodes have confirmed."""
    with _lock:
        # If no nodes expected, consider it confirmed
        if len(expected_nodes) == 0:
            return True
        return expected_nodes == confirmed_nodes


def get_countdown_seconds() -> int | None:
    """Get seconds until recording starts, or None if not in preflight."""
    with _lock:
        if current_state != "preflight" or start_at is None:
            return None
        now = datetime.now()
        return max(0, int((start_at - now).total_seconds()))


def is_preflight_expired() -> bool:
    """Check if preflight deadline has passed."""
    with _lock:
        if preflight_deadline is None:
            return False
        return datetime.now() > preflight_deadline


def reset_session():
    """Clear all session data (called on transition to idle)."""
    global session_uuid, start_at, expected_nodes, confirmed_nodes, preflight_deadline
    with _lock:
        session_uuid = None
        start_at = None
        expected_nodes = set()
        confirmed_nodes = set()
        preflight_deadline = None
