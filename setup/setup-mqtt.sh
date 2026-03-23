#!/bin/bash
# Setup and start Mosquitto MQTT broker

# Install Mosquitto and clients
sudo apt install -y mosquitto mosquitto-clients

# Enable and start service
sudo systemctl enable mosquitto
sudo systemctl start mosquitto

# Optional: show status
sudo systemctl status mosquitto --no-pager
