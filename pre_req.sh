#!/bin/bash

# Exit immediately if a command exits with a non-zero status.
set -e

echo "--- Installing prerequisites ---"

# Update package lists
sudo apt-get update -y

# Install Python and pip (if not already present)
echo "Installing Python and pip..."
sudo apt-get install -y python3 python3-pip python3-venv

# Install PostgreSQL build dependencies
# These are common dependencies for Debian/Ubuntu based systems.
# Adjust for other distributions (e.g., CentOS, Fedora) if necessary.
echo "Installing PostgreSQL build dependencies..."
sudo apt-get install -y build-essential libreadline-dev zlib1g-dev flex bison libxml2-dev libxslt-dev libssl-dev libperl-dev libpython3-dev tcl-dev

# Any Python libraries required by pg_script.py can be installed here
# For example, if configparser is not part of the standard library in the target Python version:
# echo "Installing Python libraries for pg_script.py..."
# pip3 install configparser

echo "--- Prerequisites installation complete ---"
