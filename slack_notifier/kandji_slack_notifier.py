#!/usr/bin/env python3

###############################################################################
# Title: kandji_slack_notifier.py
# Description: This script sends a Slack message to users associated with
#              devices in a specific Kandji Blueprint.
# Source: https://github.com/matdotcx/endpoint-ploughshare
# Edition: Wed 03 Sep 2024 15:30:00 PST
###############################################################################
# Setup Instructions:
# 1. Ensure you have Python 3.6 or later installed.
# 2. Install the required dependencies by running:
#    pip install httpx python-dotenv
#
# 3. Create a .env file in the same directory as this script with the following content:
#    KANDJI_SUBDOMAIN=your_subdomain
#    KANDJI_API_TOKEN=your_kandji_api_token
#    KANDJI_BLUEPRINT_ID=your_blueprint_id
#    SLACK_API_TOKEN=your_slack_api_token
#    MESSAGE_FILE_PATH=path_to_your_message_file.md  # Optional, defaults to 'message.md'
#
# 4. Ensure your Kandji API token has the following permissions:
#    - GET Device list (/api/v1/devices)
#
# 5. Ensure your Slack API token has the following scopes:
#    - users:read.email
#    - chat:write
#
# 6. Create a message.md file in the same directory as this script (or specify a different path in .env)
#    containing the message you want to send to users. Emojis and Slack flavour Markdown supported!
#
# Usage:
# python kandji_slack_notifier.py
#
# The script will:
# 1. Retrieve all devices associated with the specified Kandji Blueprint
# 2. Extract unique user emails from these devices
# 3. Look up the Slack user ID for each email
# 4. Send the message from message.md to each user via Slack
#
# Note: The script will print progress and any errors to the console.
#
# Dependencies:
# - httpx
# - python-dotenv
###############################################################################

import httpx
import json
import os
from typing import List, Dict
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Kandji:
    def __init__(self):
        self.api_token = os.getenv("KANDJI_API_TOKEN")
        self.subdomain = os.getenv("KANDJI_SUBDOMAIN")
        self.base_url = f"https://{self.subdomain}.api.kandji.io/api"
        self.headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Accept": "application/json",
        }

    def get_blueprint_devices(self, blueprint_id: str) -> List[Dict]:
        url = f"{self.base_url}/v1/devices"
        params = {"blueprint_id": blueprint_id}
        response = httpx.get(url, headers=self.headers, params=params)
        response.raise_for_status()
        return response.json()

    def get_blueprint_users(self, blueprint_id: str) -> List[str]:
        devices = self.get_blueprint_devices(blueprint_id)
        return list(set([device['user']['email'] for device in devices if device.get('user')]))

class Slack:
    def __init__(self, api_token: str):
        self.base_url = "https://slack.com/api"
        self.headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
        }

    def get_user_id(self, email: str) -> str:
        url = f"{self.base_url}/users.lookupByEmail"
        params = {"email": email}
        response = httpx.get(url, headers=self.headers, params=params)
        response.raise_for_status()
        data = response.json()
        return data['user']['id'] if data['ok'] else None

    def send_message(self, user_id: str, message: str) -> None:
        url = f"{self.base_url}/chat.postMessage"
        payload = {
            "channel": user_id,
            "text": message
        }
        response = httpx.post(url, headers=self.headers, json=payload)
        response.raise_for_status()

def read_message_from_file(file_path: str) -> str:
    with open(file_path, 'r') as file:
        return file.read().strip()

def main():
    # Load Slack API token and Blueprint ID from environment variables
    slack_api_token = os.getenv("SLACK_API_TOKEN")
    blueprint_id = os.getenv("KANDJI_BLUEPRINT_ID")
    message_file_path = os.getenv("MESSAGE_FILE_PATH", "message.md")

    if not all([slack_api_token, blueprint_id]):
        print("Please set all required environment variables (SLACK_API_TOKEN, KANDJI_BLUEPRINT_ID).")
        return

    # Initialize Kandji and Slack clients
    kandji = Kandji()
    slack = Slack(slack_api_token)

    # Get users from the specified Kandji Blueprint
    blueprint_users = kandji.get_blueprint_users(blueprint_id)

    # Read message from file
    try:
        message = read_message_from_file(message_file_path)
    except FileNotFoundError:
        print(f"Message file not found at {message_file_path}. Please check the file path.")
        return
    except IOError as e:
        print(f"Error reading message file: {str(e)}")
        return

    # Send message to each user
    for email in blueprint_users:
        user_id = slack.get_user_id(email)
        if user_id:
            try:
                slack.send_message(user_id, message)
                print(f"Message sent to {email}")
            except Exception as e:
                print(f"Failed to send message to {email}: {str(e)}")
        else:
            print(f"Could not find Slack user for email: {email}")

if __name__ == "__main__":
    main()
kandji_slack_notifier.py
