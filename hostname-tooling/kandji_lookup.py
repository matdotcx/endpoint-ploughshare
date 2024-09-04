#!/usr/bin/env python3

###############################################################################
# Title: kandji_lookup.py
# Description: This script allows you to look up the assigned user of a device
# in Kandji by providing either the device's hostname or serial number.
# Source: https://github.com/matdotcx/
# Edition: Wed 14 Aug 2024 11:53:57 BST
###############################################################################
# Setup Instructions:
# 1. Ensure you have Python 3.6 or later installed.
# 2. Install the required dependencies by running:
#    pip install requests python-dotenv
#
# 3. Create a .env file in the same directory as this script with the following content:
#    KANDJI_SUBDOMAIN=your_subdomain
#    KANDJI_API_TOKEN=your_api_token
#    KANDJI_REGION=us  # or 'eu' if you're in the EU region
#
# 4. Ensure your token has the following permissions;
#
#    GET Device details
#    /api/v1/devices/{device_id}/details
#    GET Device list
#    /api/v1/devices
#    GET Device ID
#    /api/v1/devices/{device_id}
#    GET Device Parameters
#    /api/v1/devices/{device_id}/parameters
#
# 5. Replace 'your_subdomain' and 'your_api_token' with your actual Kandji subdomain and API token.
#
#
# Usage:
# python kandji_user_lookup.py <hostname_or_serial_number>
#
# Example:
# python kandji_user_lookup.py Z1AU001HXBA-653894A
#
# Dependencies:
# - requests
# - python-dotenv
###############################################################################



import sys
import os
import requests
from requests.adapters import HTTPAdapter
import argparse
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Kandji API settings
SUBDOMAIN = os.getenv('KANDJI_SUBDOMAIN')
REGION = os.getenv('KANDJI_REGION', '')  # Default to empty string if not set
TOKEN = os.getenv('KANDJI_API_TOKEN')

# Validate required environment variables
if not all([SUBDOMAIN, TOKEN]):
    sys.exit("Error: KANDJI_SUBDOMAIN and KANDJI_API_TOKEN must be set in the .env file.")

# Determine the appropriate API base URL based on the region
if REGION in ["", "us"]:
    BASE_URL = f"https://{SUBDOMAIN}.api.kandji.io/api"
elif REGION == "eu":
    BASE_URL = f"https://{SUBDOMAIN}.api.{REGION}.kandji.io/api"
else:
    sys.exit(f'\nUnsupported region "{REGION}". Please update and try again\n')

# Kandji Management Console URL for generating device links
CONSOLE_URL = f"https://{SUBDOMAIN}.kandji.io"

# API headers for authentication and specifying content type
HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/json",
    "Content-Type": "application/json;charset=utf-8",
    "Cache-Control": "no-cache",
}

def http_errors(resp, resp_code, err_msg):
    """
    Handle HTTP errors by providing informative error messages.

    Args:
    resp (Response): The response object from the request
    resp_code (int): The HTTP status code
    err_msg (str): The error message
    """
    # Handle various HTTP status codes with appropriate messages
    if resp_code == requests.codes["bad_request"]:
        print(f"\n\tBad Request: {err_msg}")
        print(f"\tResponse: {resp.text}\n")
    elif resp_code == requests.codes["unauthorized"]:
        print("Unauthorized: Make sure you have the required permissions.")
        sys.exit(f"\t{err_msg}")
    elif resp_code == requests.codes["forbidden"]:
        print("Forbidden: The API key may be invalid or missing.")
        sys.exit(f"\t{err_msg}")
    elif resp_code == requests.codes["not_found"]:
        print(f"\nNot Found: {err_msg}")
        print(f"Response: {resp.text}")
    elif resp_code == requests.codes["too_many_requests"]:
        print("Too Many Requests: You have reached the rate limit. Try again later.")
        sys.exit(f"\t{err_msg}")
    elif resp_code == requests.codes["internal_server_error"]:
        print(f"Internal Server Error: {err_msg}")
        sys.exit()
    elif resp_code == requests.codes["service_unavailable"]:
        print("Service Unavailable: Unable to reach the service. Try again later.")
    else:
        print(f"Unexpected Error: {err_msg}")
        sys.exit()

def kandji_api(method, endpoint, params=None, payload=None):
    """
    Make an API request to the Kandji API and return the data.

    Args:
    method (str): The HTTP method (GET, POST, etc.)
    endpoint (str): The API endpoint
    params (dict, optional): Query parameters for the request
    payload (dict, optional): The request payload for POST/PUT requests

    Returns:
    dict: The JSON response from the API
    """
    # Set up a session with retry capability
    attom_adapter = HTTPAdapter(max_retries=3)
    session = requests.Session()
    session.mount(BASE_URL, attom_adapter)

    try:
        # Make the API request
        response = session.request(
            method,
            BASE_URL + endpoint,
            data=payload,
            headers=HEADERS,
            params=params,
            timeout=30,
        )

        # Attempt to parse the response as JSON
        if response:
            try:
                data = response.json()
            except Exception:
                data = response.text

        # Raise an exception for bad status codes
        response.raise_for_status()

    except requests.exceptions.RequestException as err:
        # Handle any request exceptions
        http_errors(resp=response, resp_code=response.status_code, err_msg=err)
        data = {"error": f"{response.status_code}", "api resp": f"{err}"}

    return data

def get_devices(params=None):
    """
    Retrieve all devices from the Kandji API using pagination.

    Args:
    params (dict, optional): Additional query parameters

    Returns:
    list: A list of all devices
    """
    limit = 300  # Number of devices to retrieve per request
    offset = 0   # Starting offset for pagination
    data = []    # List to store all device data

    while True:
        # Update params with pagination information
        params = params or {}
        params.update({"limit": f"{limit}", "offset": f"{offset}"})

        # Make API request to get devices
        response = kandji_api(method="GET", endpoint="/v1/devices", params=params)

        # Break the loop if no more devices are returned
        if len(response) == 0:
            break

        # Add the retrieved devices to our data list
        data.extend(response)

        # Increment the offset for the next page
        offset += limit

    return data

def find_device(search_term):
    """
    Find a device by hostname or serial number.

    Args:
    search_term (str): The hostname or serial number to search for

    Returns:
    dict: The matching device information, or None if not found
    """
    # Get all devices
    devices = get_devices()

    # Search for a device matching the search term
    for device in devices:
        if (search_term.lower() == device.get('device_name', '').lower() or
            search_term.lower() == device.get('serial_number', '').lower()):
            return device

    return None

def main():
    """Main function to run the script."""
    # Set up argument parsing
    parser = argparse.ArgumentParser(description="Look up assigned user in Kandji by device name or serial number.")
    parser.add_argument("search_term", help="The hostname or serial number of the device to look up.")
    args = parser.parse_args()

    print(f"Searching for device: {args.search_term}")

    # Find the device
    device = find_device(args.search_term)

    if device:
        # Extract and display device information
        user_info = device.get('user', {})
        device_id = device.get('device_id')
        device_link = f"{CONSOLE_URL}/devices/{device_id}" if device_id else "N/A"

        print(f"\nDevice Information:")
        print(f"Device Name: {device.get('device_name')}")
        print(f"Serial Number: {device.get('serial_number')}")
        if isinstance(user_info, dict):
            print(f"Assigned User: {user_info.get('name', 'N/A')}")
            print(f"User Email: {user_info.get('email', 'N/A')}")
        else:
            print(f"Assigned User: {user_info}")
            print("User Email: N/A")
        print(f"Device Link: {device_link}")
    else:
        print(f"\nNo device found matching '{args.search_term}'")

if __name__ == "__main__":
    main()
