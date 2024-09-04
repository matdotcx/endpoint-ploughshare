#!/bin/bash

###############################################################################
# Title: set_computer_name.sh
# Description: This script assembles and sets a computer name based on the 
#              model number and hardware UUID for macOS devices.
# Source: https://github.com/matdotcx/endpoint-ploughshare/
# Edition: Wed 04 Sep 2024 15:30:00 BST
###############################################################################
# Setup Instructions:
# 1. Ensure you have bash shell access on the target macOS device.
# 2. This script requires root privileges to set the computer name.
#
# Usage:
# sudo bash set_computer_name.sh
#
# The script will:
# 1. Extract the model number from system_profiler output
# 2. Clean the model number to make it suitable for a hostname
# 3. Extract a specified number of digits from the end of the hardware UUID
# 4. Combine the cleaned model number and UUID digits to create a unique name
# 5. Set the computer name, hostname, and local hostname using the generated name
# - Example Hostname Z1AU001HXBA-653894A
#   - Model Number: Z1AU001HXBA + UUID Extract 653894A
#
# Note: This script is compatible with macOS Monterey and higher.
#
# Script behavior:
# - The script uses 'awk' to parse system_profiler output for backwards compatibility.
# - It removes special characters from the generated name to ensure hostname validity.
# - The number of UUID digits used can be adjusted by changing the 'numDigits' variable.
# - The script will exit with an error if:
#   - It fails to parse the identifier correctly
#   - It's not run with root privileges
#   - It can't determine a valid computer name
#
# Dependencies:
# - system_profiler (built-in macOS utility)
# - awk (built-in macOS utility)
# - scutil (built-in macOS utility)
#
# Customization:
# - To adjust the number of UUID digits used, modify the 'numDigits' variable (default: 7)
###############################################################################

# Get the model number to use as the prefix
prefix=$(system_profiler -xml SPHardwareDataType | awk -F'[<>]' '/<key>model_number<\/key>/{getline; print $3; exit}')

# Clean the prefix to make it suitable for a hostname
# Remove any "/" characters (common in model numbers like "Z1AU001HXB/A")
prefix=$(echo "$prefix" | tr -d "/")

# use hardwareUUID as identifier
identifier=$(system_profiler SPHardwareDataType | awk '/Hardware UUID/ {print $NF}')

# use n digits of the identifier
# depending on your fleet size, 4-6 digits are sensible values
numDigits=7

# get trailing digits (works best with UUID)
offset=$((${#identifier} - numDigits))

digits=${identifier:${offset}:${numDigits}}

# verify we actually got the right number of digits
if [[ ${#digits} -ne ${numDigits} ]]; then
    echo "something went wrong parsing the identifier, $identifier, $digits"
    exit 2
fi

# assemble the name
name="${prefix}-${digits}"

# clean out special chars for hostnames
hname=$(tr -d "[:blank:]'&()*%$\"\\\-~?!<>[]{}=+:;,.|^#@" <<< "${name}")

# check if running as root
if [[ $EUID -ne 0 ]]; then
    echo "this script needs to run as root"
    echo "cannot set computer name to ${name} (${hname})"
    exit 3
fi

if [[ "$name" != "" ]]; then
    echo "Setting Computer name to ${name}"
    echo "Setting Hostname to ${hname}"
    
    scutil --set ComputerName "${name}"
    scutil --set HostName "${hname}"
    scutil --set LocalHostName "${hname}"
else
    echo "could not determine computer name, exiting"
    exit 4
fi
