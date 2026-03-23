# mqtt_client.py - MQTT client for publishing and subscribing
import json
import logging
import threading
import time
import paho.mqtt.client as mqtt
import state
from config import settings

logger = logging.getLogger(__name__)


class MQTTClient:
    def __init__(self):
        self.broker = settings.mqtt_broker
        self.port = settings.mqtt_port
        self.topic_prefix = settings.mqtt_topic_prefix
        self.connected = False
        self._stop_event = threading.Event()
        self._node_confirmation_callback = None

        self.client = mqtt.Client()
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message

        # Start connection in background (non-blocking)
        self._connect_thread = threading.Thread(target=self._connect_with_retry, daemon=True)
        self._connect_thread.start()

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self.connected = True
            logger.info(f"[MQTT] Connected to {self.broker}:{self.port}")
            # Subscribe to node ready messages
            topic = f"{self.topic_prefix}/node/+/ready"
            self.client.subscribe(topic)
            logger.info(f"[MQTT] Subscribed to {topic}")
        else:
            logger.error(f"[MQTT] Connection failed with code {rc}")

    def _on_disconnect(self, client, userdata, rc):
        self.connected = False
        if rc != 0:
            logger.warning(f"[MQTT] Unexpected disconnect (rc={rc}), will reconnect...")

    def _on_message(self, client, userdata, msg):
        """Handle incoming MQTT messages."""
        try:
            # Parse topic: ctlr/node/{node_id}/ready
            topic_parts = msg.topic.split("/")
            if len(topic_parts) >= 4 and topic_parts[-1] == "ready":
                node_id = topic_parts[-2]
                payload = json.loads(msg.payload.decode())

                if payload.get("ready", False):
                    logger.info(f"[MQTT] Node {node_id} confirmed ready")
                    all_confirmed = state.confirm_node(node_id)
                    if all_confirmed and self._node_confirmation_callback:
                        self._node_confirmation_callback()
                else:
                    error = payload.get("error", "Unknown error")
                    logger.warning(f"[MQTT] Node {node_id} reported error: {error}")
        except Exception as e:
            logger.error(f"[MQTT] Error processing message: {e}")

    def set_node_confirmation_callback(self, callback):
        """Set callback to be called when all nodes are confirmed."""
        self._node_confirmation_callback = callback

    def _connect_with_retry(self):
        """Connect to broker with exponential backoff retry."""
        backoff = 1
        max_backoff = 60

        while not self._stop_event.is_set():
            try:
                self.client.connect(self.broker, self.port, 60)
                self.client.loop_start()
                return  # Success, exit retry loop
            except Exception as e:
                logger.error(f"[MQTT] Connection failed: {e}. Retrying in {backoff}s...")
                self._stop_event.wait(backoff)
                backoff = min(backoff * 2, max_backoff)

    def publish_status(self):
        """Publish current state to MQTT status topic."""
        if not self.connected:
            logger.debug("[MQTT] Not connected, skipping status publish")
            return

        try:
            payload = state.get_snapshot()
            topic = f"{self.topic_prefix}/status"
            self.client.publish(topic, json.dumps(payload), retain=True)
        except Exception as e:
            logger.error(f"[MQTT] Status publish failed: {e}")

    def publish_command(self, action: str, data: dict | None = None):
        """Publish a command to nodes."""
        if not self.connected:
            logger.debug("[MQTT] Not connected, skipping command publish")
            return

        try:
            payload = {"action": action, "uuid": state.session_uuid}
            if data:
                payload.update(data)
            topic = f"{self.topic_prefix}/command"
            self.client.publish(topic, json.dumps(payload))
            logger.info(f"[MQTT] Published command: {action}")
        except Exception as e:
            logger.error(f"[MQTT] Command publish failed: {e}")

    def broadcast_countdown(self, seconds: int):
        """Broadcast countdown to all nodes."""
        if not self.connected:
            return

        try:
            payload = {
                "state": "preflight",
                "uuid": state.session_uuid,
                "countdown": seconds,
                "action": "countdown"
            }
            topic = f"{self.topic_prefix}/status"
            self.client.publish(topic, json.dumps(payload))
        except Exception as e:
            logger.error(f"[MQTT] Countdown broadcast failed: {e}")

    def stop(self):
        """Graceful shutdown."""
        self._stop_event.set()
        self.client.loop_stop()
        self.client.disconnect()
