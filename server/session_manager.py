# session_manager.py - State machine and session coordination
import logging
import threading
import uuid
from datetime import datetime, timedelta

import state
from config import settings

logger = logging.getLogger(__name__)

# State machine transitions
TRANSITIONS = {
    "idle": ["preflight"],
    "preflight": ["recording", "idle"],
    "recording": ["finishing"],
    "finishing": ["idle"]
}


class SessionManager:
    def __init__(self):
        self._observers = []
        self._countdown_thread = None
        self._countdown_stop = threading.Event()
        self._transition_lock = threading.Lock()
        self._mqtt_client = None

    def set_mqtt_client(self, mqtt_client):
        """Set the MQTT client for broadcasting."""
        self._mqtt_client = mqtt_client

    def subscribe(self, callback):
        """Subscribe to state change notifications."""
        self._observers.append(callback)

    def notify(self):
        """Notify all observers of state change."""
        for callback in self._observers:
            try:
                callback()
            except Exception as e:
                logger.error(f"[Session] Observer callback failed: {e}")

    def _transition(self, new_state: str) -> bool:
        """Internal state transition (must hold lock)."""
        current = state.get_current_state()
        allowed = TRANSITIONS.get(current, [])

        if new_state not in allowed:
            return False

        state.update_session(new_state)
        logger.info(f"[Session] Transitioned: {current} → {new_state}")
        return True

    def start_preflight(self, start_in: int, nodes: list[str]) -> tuple[bool, str]:
        """
        Start preflight phase with scheduled recording.
        
        Args:
            start_in: Seconds until recording starts
            nodes: List of node IDs that must confirm ready
        
        Returns:
            (success, message) tuple
        """
        if start_in <= 0:
            return False, "start_in must be positive"

        with self._transition_lock:
            current = state.get_current_state()
            if current != "idle":
                return False, f"Cannot start preflight from {current}"

            # Generate session UUID
            session_uuid = str(uuid.uuid4())
            state.update_session("preflight", session_uuid)

            # Calculate times
            now = datetime.now()
            start_at = now + timedelta(seconds=start_in)
            preflight_deadline = now + timedelta(seconds=settings.preflight_timeout)

            # Setup coordination
            state.setup_preflight(start_at, nodes, preflight_deadline)

            logger.info(f"[Session] Preflight started: uuid={session_uuid}, "
                       f"start_in={start_in}s, nodes={nodes}")

        # Broadcast prepare command to nodes
        if self._mqtt_client:
            self._mqtt_client.publish_command("prepare", {
                "start_at": start_at.isoformat(),
                "nodes": nodes
            })

        # Start countdown thread
        self._start_countdown_thread()

        self.notify()
        return True, session_uuid

    def _start_countdown_thread(self):
        """Start background thread to manage preflight countdown."""
        self._countdown_stop.clear()

        def countdown_loop():
            logger.info("[Session] Countdown thread started")
            broadcast_interval = settings.countdown_broadcast_interval

            while not self._countdown_stop.is_set():
                current = state.get_current_state()
                if current != "preflight":
                    break

                # Check if preflight timeout expired
                if state.is_preflight_expired():
                    logger.warning("[Session] Preflight timeout - not all nodes confirmed")
                    self._abort_preflight("Preflight timeout")
                    break

                # Check countdown
                countdown = state.get_countdown_seconds()
                if countdown is None:
                    break

                # Only broadcast countdown if all nodes confirmed
                if state.all_nodes_confirmed():
                    if self._mqtt_client:
                        self._mqtt_client.broadcast_countdown(countdown)
                    
                    if countdown <= 0:
                        # Time to start recording
                        self._start_recording()
                        break

                self._countdown_stop.wait(broadcast_interval)

            logger.info("[Session] Countdown thread stopped")

        self._countdown_thread = threading.Thread(target=countdown_loop, daemon=True)
        self._countdown_thread.start()

    def _start_recording(self):
        """Transition from preflight to recording."""
        with self._transition_lock:
            if state.get_current_state() != "preflight":
                return

            self._transition("recording")

        if self._mqtt_client:
            self._mqtt_client.publish_command("start")

        self.notify()
        logger.info("[Session] Recording started")

    def _abort_preflight(self, reason: str):
        """Abort preflight and return to idle."""
        with self._transition_lock:
            if state.get_current_state() != "preflight":
                return

            self._transition("idle")
            state.reset_session()

        if self._mqtt_client:
            self._mqtt_client.publish_command("abort", {"reason": reason})

        self.notify()
        logger.warning(f"[Session] Preflight aborted: {reason}")

    def cancel(self) -> tuple[bool, str]:
        """Cancel preflight and return to idle."""
        with self._transition_lock:
            current = state.get_current_state()
            if current != "preflight":
                return False, f"Cannot cancel from {current} state"

            # Stop countdown thread
            self._countdown_stop.set()

            self._transition("idle")
            state.reset_session()

        if self._mqtt_client:
            self._mqtt_client.publish_command("abort", {"reason": "User cancelled"})

        self.notify()
        return True, "Preflight cancelled"

    def stop_recording(self) -> tuple[bool, str]:
        """Stop recording and transition to finishing."""
        with self._transition_lock:
            current = state.get_current_state()
            if current != "recording":
                return False, f"Cannot stop from {current} state"

            self._transition("finishing")

        if self._mqtt_client:
            self._mqtt_client.publish_command("stop")

        self.notify()

        # Start cleanup in background
        self._start_cleanup()

        return True, "Stopping recording"

    def _start_cleanup(self):
        """Start cleanup process after recording stops."""
        def cleanup():
            logger.info("[Session] Cleanup started")
            try:
                # TODO: Add actual cleanup logic here
                # - Flush buffers
                # - Close file handles
                # - Finalize metadata
                pass
            except Exception as e:
                logger.error(f"[Session] Cleanup failed: {e}")
            finally:
                # Always transition to idle
                with self._transition_lock:
                    if state.get_current_state() == "finishing":
                        self._transition("idle")
                        state.reset_session()
                
                if self._mqtt_client:
                    self._mqtt_client.publish_command("cleanup_complete")
                
                self.notify()
                logger.info("[Session] Cleanup complete, now idle")

        threading.Thread(target=cleanup, daemon=True).start()

    def on_all_nodes_confirmed(self):
        """Called when all nodes have confirmed ready."""
        logger.info("[Session] All nodes confirmed ready")
        # Countdown thread will handle the rest
