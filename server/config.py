# config.py - Application configuration
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # MQTT
    mqtt_broker: str = "localhost"
    mqtt_port: int = 1883
    mqtt_topic_prefix: str = "ctlr"

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # Timing
    telemetry_interval: int = 2
    preflight_timeout: int = 30
    countdown_broadcast_interval: int = 1

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

    @property
    def mqtt_status_topic(self) -> str:
        return f"{self.mqtt_topic_prefix}/status"

    @property
    def mqtt_command_topic(self) -> str:
        return f"{self.mqtt_topic_prefix}/command"

    @property
    def mqtt_node_ready_topic(self) -> str:
        return f"{self.mqtt_topic_prefix}/node/+/ready"


settings = Settings()
