#!/usr/bin/env python3

###############################################################################
# Title: auto_app_updater.py
# Description: Updates a Custom App in Kandji with the latest version
#             from a manifest JSON. Ideal for your CI runner actions!
# Source: https://github.com/matdotcx/endpoint-ploughshare/
# Edition: Fri 18 Oct 2024 12:16:09 BST
# ###############################################################################

# Setup Instructions:
# 1. Ensure you have Python 3.6 or later installed.
# 2. Install the required dependencies by running:
#    pip install requests python-dotenv
#
# 3. Create a .env file in the same directory as this script with:
#    # Kandji API Configuration
#    KANDJI_SUBDOMAIN=your_subdomain
#    KANDJI_API_TOKEN=your_api_token
#    KANDJI_REGION=us
#
#    # App Configuration
#    APP_ID=your_app_id
#    APP_NAME=YourApp.app
#    MANIFEST_URL=https://your.manifest.url/manifest.json
#
#    # Optional Configuration
#    APP_INSTALL_TYPE=zip
#    APP_INSTALL_ENFORCEMENT=continuously_enforce
#    APP_SHOW_IN_SELF_SERVICE=true
#    APP_SELF_SERVICE_CATEGORY_ID=your_category_id
#
# Usage:
# python auto_app_updater.py [--dry-run] [--debug]
#
# Options:
#   --dry-run    Validate and preview without making changes
#   --debug      Show debug output in console (default with --dry-run)
#
# Examples:
#   python auto_app_updater.py
#   python auto_app_updater.py --debug
#   python auto_app_updater.py --dry-run
###############################################################################

import sys
import os
import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
import argparse
import logging
import tempfile
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
import json
import distutils.util
import time

# Load environment variables
load_dotenv()

# App Configuration
APP_ID = os.getenv('APP_ID')
APP_NAME = os.getenv('APP_NAME')
MANIFEST_URL = os.getenv('MANIFEST_URL')

# Optional App Configuration with defaults
APP_INSTALL_TYPE = os.getenv('APP_INSTALL_TYPE', 'package')
APP_INSTALL_ENFORCEMENT = os.getenv('APP_INSTALL_ENFORCEMENT', 'install_once')
try:
    APP_SHOW_IN_SELF_SERVICE = bool(distutils.util.strtobool(os.getenv('APP_SHOW_IN_SELF_SERVICE', 'false')))
except ValueError:
    APP_SHOW_IN_SELF_SERVICE = False
APP_SELF_SERVICE_CATEGORY_ID = os.getenv('APP_SELF_SERVICE_CATEGORY_ID')

# Validate required app configuration
if not all([APP_ID, APP_NAME, MANIFEST_URL]):
    sys.exit("Error: APP_ID, APP_NAME, and MANIFEST_URL must be set in the .env file.")

# Kandji API Configuration
SUBDOMAIN = os.getenv('KANDJI_SUBDOMAIN')
REGION = os.getenv('KANDJI_REGION', '')
TOKEN = os.getenv('KANDJI_API_TOKEN')

# Validate required Kandji configuration
if not all([SUBDOMAIN, TOKEN]):
    sys.exit("Error: KANDJI_SUBDOMAIN and KANDJI_API_TOKEN must be set in the .env file.")

# Determine the appropriate API base URL based on the region
if REGION in ["", "us"]:
    BASE_URL = f"https://{SUBDOMAIN}.api.kandji.io/api"
elif REGION == "eu":
    BASE_URL = f"https://{SUBDOMAIN}.api.{REGION}.kandji.io/api"
else:
    sys.exit(f'\nUnsupported region "{REGION}". Please update and try again\n')

# API headers
HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/json",
    "Content-Type": "application/json;charset=utf-8",
    "Cache-Control": "no-cache",
}

USER_AGENT = f"Kandji-App-Updater/1.0 ({APP_NAME})"

# Set up logging
log_filename = f"kandji_{APP_NAME.replace('.', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

# Global logger
logger = None

def setup_logging(debug_mode):
    global logger
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)

    # File handler (always debug level)
    file_handler = logging.FileHandler(log_filename)
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

    # Console handler (info level by default, debug level if debug_mode is True)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG if debug_mode else logging.INFO)
    console_formatter = logging.Formatter('%(levelname)s - %(message)s')
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

class KandjiAPIError(Exception):
    """Custom exception for Kandji API errors"""
    pass

def create_session():
    """Create a session with retry configuration"""
    session = requests.Session()
    retry_strategy = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[500, 502, 503, 504],
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.headers.update(HEADERS)
    return session

def handle_api_error(response, operation):
    """Centralized error handling for API responses"""
    error_msg = f"Error during {operation}: {response.status_code}"
    try:
        error_detail = response.json()
        logger.debug(f"Error details: {json.dumps(error_detail, indent=2)}")
    except:
        error_detail = response.text
        logger.debug(f"Error response: {error_detail}")

    if response.status_code == 503:
        logger.warning(f"Service Unavailable (503) during {operation}. This may be retried.")
    else:
        logger.error(error_msg)

    response.raise_for_status()

def api_request(method, endpoint, session, **kwargs):
    """Make an API request with proper error handling"""
    url = f"{BASE_URL}{endpoint}"
    response = session.request(method, url, **kwargs)

    try:
        response.raise_for_status()
        return response.json() if response.content else None
    except requests.exceptions.RequestException as e:
        handle_api_error(response, f"{method} {endpoint}")
        raise

def get_manifest():
    """Fetch and parse the manifest JSON."""
    logger.info("Fetching manifest...")
    try:
        response = requests.get(
            MANIFEST_URL,
            headers={'User-Agent': USER_AGENT},
            timeout=30
        )
        response.raise_for_status()

        manifest = response.json()
        logger.debug(f"Manifest content: {json.dumps(manifest, indent=2)}")

        current_release = manifest.get('currentRelease')
        for release in manifest.get('releases', []):
            if release.get('version') == current_release:
                download_url = release.get('updateTo', {}).get('url')
                version = release.get('version')
                logger.info(f"Found version {version} with download URL")
                return download_url, version

        raise KandjiAPIError("Failed to find download URL in manifest")
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to fetch manifest: {str(e)}")
        raise

def download_zip(url):
    """Download the ZIP file to a temporary location."""
    logger.info(f"Downloading ZIP from {url}...")
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as temp_file:
            response = requests.get(
                url,
                headers={'User-Agent': USER_AGENT},
                stream=True,
                timeout=30
            )
            response.raise_for_status()
            for chunk in response.iter_content(chunk_size=8192):
                temp_file.write(chunk)
        logger.debug(f"ZIP downloaded to {temp_file.name}")
        return temp_file.name
    except Exception as e:
        logger.error(f"Failed to download ZIP: {str(e)}")
        raise

def get_app_details():
    """Fetch current app details from Kandji."""
    logger.info(f"Fetching details for {APP_NAME}...")
    session = create_session()
    return api_request('GET', f"/v1/library/custom-apps/{APP_ID}", session)

def upload_to_s3(file_path):
    """Upload the ZIP file to S3 via Kandji API."""
    logger.info("Preparing S3 upload...")
    session = create_session()

    upload_filename = f"{APP_NAME.replace('.app', '')}.zip"

    # Get upload URL and details
    upload_details = api_request(
        'POST',
        "/v1/library/custom-apps/upload",
        session,
        json={"name": upload_filename}
    )

    logger.debug(f"S3 upload details: {json.dumps(upload_details, indent=2)}")

    # Upload to S3
    try:
        s3_url = upload_details['post_url']
        post_data = upload_details['post_data']

        logger.info("Uploading to S3...")
        with open(file_path, 'rb') as file:
            files = {'file': (upload_filename, file)}
            response = requests.post(s3_url, data=post_data, files=files)
            response.raise_for_status()

        logger.info("S3 upload complete.")

        # Add a 30-second wait after the S3 upload
        logger.info("Waiting 30 seconds for upload processing...")
        time.sleep(30)
        logger.info("Wait complete.")

        return upload_details['file_key']
    except Exception as e:
        logger.error(f"Failed to upload to S3: {str(e)}")
        raise

def update_app(file_key, current_settings, version):
    """Update the existing app with new file key while maintaining settings."""
    logger.info(f"Updating {APP_NAME} to version {version} in Kandji...")
    session = create_session()

    payload = {
        "name": APP_NAME,
        "file_key": file_key,
        "install_type": current_settings.get('install_type', APP_INSTALL_TYPE),
        "install_enforcement": current_settings.get('install_enforcement', APP_INSTALL_ENFORCEMENT),
        "show_in_self_service": current_settings.get('show_in_self_service', APP_SHOW_IN_SELF_SERVICE),
        "active": current_settings.get('active', True)
    }

    # Include existing scripts and settings
    if current_settings:
        for script_type in ['audit_script', 'preinstall_script', 'postinstall_script']:
            if current_settings.get(script_type):
                payload[script_type] = current_settings[script_type]

        if current_settings.get('unzip_location'):
            payload['unzip_location'] = current_settings['unzip_location']

    # Handle self-service settings
    if payload['show_in_self_service']:
        payload["self_service_category_id"] = current_settings.get('self_service_category_id') or APP_SELF_SERVICE_CATEGORY_ID

    logger.debug(f"Update payload: {json.dumps(payload, indent=2)}")
    return api_request('PATCH', f"/v1/library/custom-apps/{APP_ID}", session, json=payload)

def main(dry_run=False, debug=False):
    """Main execution function"""
    setup_logging(debug)

    logger.info(f"Starting {APP_NAME} update process...")
    zip_path = None

    try:
        # Get manifest information
        zip_url, version = get_manifest()
        if not zip_url:
            raise KandjiAPIError("Failed to find download URL in manifest.")

        # Get current app details
        current_app_details = get_app_details()
        logger.debug(f"Current app details: {json.dumps(current_app_details, indent=2)}")

        # Prepare summary information
        summary = f"{'DRY RUN: Would download' if dry_run else 'Downloaded'} {APP_NAME} version {version} from: {zip_url}"
        summary += f"\n{'DRY RUN: Would upload' if dry_run else 'Uploaded'} to S3 and update{'d' if not dry_run else ''} app with current settings"
        summary += f"\nApp settings {'that would be' if dry_run else 'that were'} maintained:"
        summary += f"\n         - Install type: {current_app_details.get('install_type', APP_INSTALL_TYPE)}"
        summary += f"\n         - Install enforcement: {current_app_details.get('install_enforcement', APP_INSTALL_ENFORCEMENT)}"
        summary += f"\n         - Show in Self Service: {current_app_details.get('show_in_self_service', APP_SHOW_IN_SELF_SERVICE)}"

        # Handle dry run
        if dry_run:
            logger.info("Dry run summary:")
            logger.info(summary)
            return True

        # Download and update
        zip_path = download_zip(zip_url)
        file_key = upload_to_s3(zip_path)
        update_result = update_app(file_key, current_app_details, version)

        logger.info(f"Update to version {version} successful!")
        logger.debug(f"Update result: {json.dumps(update_result, indent=2)}")

        # Log the summary for actual runs
        logger.info("Update Summary:")
        logger.info(summary)

        return True

    except Exception as e:
        logger.error(f"Failed to update {APP_NAME}: {str(e)}")
        return False

    finally:
        if zip_path:
            logger.info("Cleaning up temporary files...")
            try:
                os.unlink(zip_path)
            except Exception as e:
                logger.warning(f"Failed to clean up temporary file {zip_path}: {str(e)}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=f"Update {APP_NAME} in Kandji")
    parser.add_argument('--dry-run', action='store_true', help='Validate and preview without making changes')
    parser.add_argument('--debug', action='store_true', help='Show debug output in console')
    args = parser.parse_args()

    # If dry-run is set, automatically set debug to True as well
    if args.dry_run:
        args.debug = True

    success = main(dry_run=args.dry_run, debug=args.debug)
    sys.exit(0 if success else 1)
