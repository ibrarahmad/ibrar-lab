#!/bin/bash

set -e

echo "--- Installing prerequisites ---"

detect_os() {
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        OS=$ID
    else
        echo "Cannot detect OS. Exiting."
        exit 1
    fi
}

install_debian_deps() {
    echo "Detected OS: $OS"
    sudo apt-get update -y
    echo "Installing Python and pip..."
    sudo apt-get install -y python3 python3-pip python3-venv
    echo "Installing PostgreSQL build dependencies..."
    sudo apt-get install -y build-essential libreadline-dev zlib1g-dev flex bison \
        libxml2-dev libxslt-dev libssl-dev libperl-dev libpython3-dev tcl-dev
}

install_redhat_deps() {
    echo "Detected OS: $OS"
    sudo yum update -y
    echo "Installing Python and pip..."
    sudo yum install -y python3 python3-pip
    # python3-venv is not available on RHEL/CentOS/Rocky, skip it
    echo "Installing PostgreSQL build dependencies..."
    sudo yum groupinstall -y "Development Tools"
    sudo yum install -y readline-devel zlib-devel flex bison libxml2-devel \
        libxslt-devel openssl-devel perl-devel python3-devel tcl-devel
}

install_python_libs() {
    echo "Installing required Python libraries for pg_script.py..."
    pip3 install --user argparse configparser
}

main() {
    detect_os
    if [[ "$OS" == "ubuntu" || "$OS" == "debian" ]]; then
        install_debian_deps
    elif [[ "$OS" == "centos" || "$OS" == "rhel" || "$OS" == "fedora" || "$OS" == "rocky" ]]; then
        install_redhat_deps
    else
        echo "Unsupported OS: $OS"
        exit 1
    fi

    install_python_libs

    echo "--- Prerequisites installation complete ---"
}

main