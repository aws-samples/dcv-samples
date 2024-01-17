#!/bin/bash
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
#
# Permission is hereby granted, free of charge, to any person obtaining a copy of this
# software and associated documentation files (the "Software"), to deal in the Software
# without restriction, including without limitation the rights to use, copy, modify,
# merge, publish, distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A
# PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT
# HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
# SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

# NICE DCV Connection Gateway Installer Script

set -eE

# Retrieve System Info
read -r system version <<<$(echo $(cat /etc/os-release | grep "^ID=\|^VERSION_ID=" | sort | cut -d"=" -f2 | tr -d "\"" | tr '[:upper:]' '[:lower:]'))
major_version="${version%.*}"
arch="$(arch)"
CLOUDFRONT_PREFIX="https://d1uj6qtbmh3dt5.cloudfront.net"
TMP_DIR="$(mktemp -d /tmp/XXXXXX)"
trap 'rm -rf -- "$TMP_DIR"' ERR

case $system in
    amzn )
        if [ "$major_version" = 2 ]; then
            package_type="el7"
            package_manager="yum"
            package_extension="rpm"
        fi
        ;;
    centos|rhel )
        if [[ "$major_version" =~ ^(7|8|9) ]]; then
            package_type="el$major_version"
            if [[ "$major_version" =~ ^(8|9) ]]; then
              package_manager="dnf"
            else
              package_manager="yum"
            fi
            package_extension="rpm"      
        fi
        ;;
    ubuntu )
        if [ "$major_version" = 22 ] || [ "$major_version" = 20 ]; then
            package_type="ubuntu$(echo $version | tr -d '.')"
            package_manager="apt"
            package_extension="deb"
        fi
        ;;
    * )
        echo "Error: system '$system' is not supported"
        exit 1
        ;;
esac

if [ -z "$package_type" ]; then
    echo "Error: system '$system' with version '$version' is not supported for arch '$arch'"
    exit 1
fi

# Download Packages
if [ "$package_manager" = apt ]; then
    curl -o "$TMP_DIR/NICE-GPG-KEY" "$CLOUDFRONT_PREFIX/NICE-GPG-KEY"
    gpg --import "$TMP_DIR/NICE-GPG-KEY"
    if [ $arch != "x86_64" ]; then
        deb_arch="arm64"
        curl -o "$TMP_DIR/nice-dcv-server.tgz" "$CLOUDFRONT_PREFIX/nice-dcv-ubuntu2204-aarch64.tgz"
    else
        deb_arch="amd64" 
        curl -o "$TMP_DIR/nice-dcv-server.tgz" "$CLOUDFRONT_PREFIX/nice-dcv-$package_type-$arch.tgz"
    fi
    curl -o "$TMP_DIR/nice-dcv-connection-gateway.$package_extension" "$CLOUDFRONT_PREFIX/nice-dcv-connection-gateway_$deb_arch.$package_type.$package_extension"
else
    rpm --import "$CLOUDFRONT_PREFIX"/NICE-GPG-KEY
    curl -o "$TMP_DIR/nice-dcv-connection-gateway.$package_extension" "$CLOUDFRONT_PREFIX/nice-dcv-connection-gateway-$package_type.$arch.$package_extension"
    curl -o "$TMP_DIR/nice-dcv-server.tgz" "$CLOUDFRONT_PREFIX/nice-dcv-$package_type-$arch.tgz"
fi 

# Install Packages
tar -xvzf "$TMP_DIR/nice-dcv-server.tgz" -C "$TMP_DIR"
for package_pattern in "nice-dcv-web-viewer*" "nice-dcv-connection-gateway.$package_extension"; do
    package_full_path=$(find "$TMP_DIR" -name "$package_pattern")
    "$package_manager" install -y "$package_full_path"
done

# Configure Gateway
## Enables Web Access through the Gateway
sed -i --expression 's|url = "https://localhost:8080"|local-resources-path = "/usr/share/dcv/www"|' /etc/dcv-connection-gateway/dcv-connection-gateway.conf
## Uncomment the line below to add your Session Resolver and replace the placeholder
#sed -i --expression 's|url = "https://localhost:8081"|url = "https://RESOLVER-URL"|' /etc/dcv-connection-gateway/dcv-connection-gateway.conf

# Enable and start Gateway
systemctl enable dcv-connection-gateway
systemctl start dcv-connection-gateway

# Clean Up
rm -rf "$TMP_DIR"
