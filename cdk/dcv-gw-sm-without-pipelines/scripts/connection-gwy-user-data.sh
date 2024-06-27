#!/bin/bash
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
#
# Permission is hereby granted, free of charge, to any person obtaining a copy of
# this software and associated documentation files (the "Software"), to deal in
# the Software without restriction, including without limitation the rights to
# use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of
# the Software, and to permit persons to whom the Software is furnished to do so.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS
# FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
# COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER
# IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
# CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

LOG_PATH="/var/log/dcv-connection-gwy-install.log"
echo $(date -u) "*****START USER DATA SCRIPT*****" | tee -a "$LOG_PATH"

# Retrieve System Info
echo $(date -u) "Discovering OS Info" | tee -a "$LOG_PATH"
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
echo $(date -u) "Discovered OS:" | tee -a "$LOG_PATH"
echo $(date -u) "Arch: $arch" | tee -a "$LOG_PATH"
echo $(date -u) "OS Type: $package_type" | tee -a "$LOG_PATH"
echo $(date -u) "Package Manager: $package_manager" | tee -a "$LOG_PATH"
echo $(date -u) "Package Extension: $package_extension" | tee -a "$LOG_PATH"

# Download Packages
echo $(date -u) "Downloading DCV Connection Gateway Packages" | tee -a "$LOG_PATH"
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
echo $(date -u) "Installing DCV Connection Gateway" | tee -a "$LOG_PATH"
tar -xvzf "$TMP_DIR/nice-dcv-server.tgz" -C "$TMP_DIR"
for package_pattern in "nice-dcv-web-viewer*" "nice-dcv-connection-gateway.$package_extension"; do
    package_full_path=$(find "$TMP_DIR" -name "$package_pattern")
    "$package_manager" install -y "$package_full_path"
done

# Enables Web Access through the Gateway
sed -i --expression 's|url = "https://localhost:8080"|local-resources-path = "/usr/share/dcv/www"|' /etc/dcv-connection-gateway/dcv-connection-gateway.conf

# Enable and start Gateway
systemctl enable dcv-connection-gateway
systemctl start dcv-connection-gateway

# Clean Up
rm -rf "$TMP_DIR"

# Get current region
TOKEN=`curl -X PUT "http://169.254.169.254/latest/api/token" -H "X-aws-ec2-metadata-token-ttl-seconds: 21600"`
REGION=$(curl -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/placement/region)
echo $(date -u) "Current Region: $REGION" | tee -a "$LOG_PATH"

# Retrieve Broker Private DNS from SSM Parameter Store
echo $(date -u) "Retrieving broker private DNS from SSM Parameter Store" | tee -a "$LOG_PATH"
BROKER_PRIVATE_DNS=$(aws ssm get-parameter --name dcv-broker-private-dns --region "$REGION" --with-decryption | grep -Po '"Value": "\K[^"]*')
timeout 1 bash -c "/dev/tcp/$BROKER_PRIVATE_DNS/8447"
RESPONSE="$?"
while [ "$RESPONSE" != 0 ]; do
    echo $(date -u) "Unable to reach broker. Waiting before retry." | tee -a "$LOG_PATH"
    sleep 15s
    BROKER_PRIVATE_DNS=$(aws ssm get-parameter --name dcv-broker-private-dns --region "$REGION" --with-decryption | grep -Po '"Value": "\K[^"]*')
    timeout 1 bash -c "cat < /dev/null > /dev/tcp/$BROKER_PRIVATE_DNS/8447"
    RESPONSE="$?"
done
echo $(date -u) "Broker private DNS found $BROKER_PRIVATE_DNS" | tee -a "$LOG_PATH"

# Port Configuration. Using hex to escape double quotes: \x22 = "
echo $(date -u) "Configuring Connection Gateway..." | tee -a "$LOG_PATH"
sed -i "s/^#\[health-check\]/\[health-check\]/g" /etc/dcv-connection-gateway/dcv-connection-gateway.conf
sed -i --expression 's|#bind-addr = "::"|bind-addr = "::"|' /etc/dcv-connection-gateway/dcv-connection-gateway.conf
sed -i --expression 's|#tls-strict = false|tls-strict = false|' /etc/dcv-connection-gateway/dcv-connection-gateway.conf
sed -i "/\[resolver\]/a tls-strict = false" /etc/dcv-connection-gateway/dcv-connection-gateway.conf
sed -i "/bind-addr = \"::\"/a port = 8989" /etc/dcv-connection-gateway/dcv-connection-gateway.conf
sed -i "s|url = \"https://localhost:8081\"|url = \"https://$BROKER_PRIVATE_DNS:8447\"|" /etc/dcv-connection-gateway/dcv-connection-gateway.conf

# Start DCV Connection Gateway Service
echo $(date -u) "Starting and Enabling Connection Gateway service..." | tee -a "$LOG_PATH"
systemctl restart dcv-connection-gateway.service

# Log if successful installation
if [[ $? -eq 0 ]]; then
    echo $(date -u) "Successfully installed DCV Connection Gateway" | tee -a "$LOG_PATH"
else
    echo $(date -u) "There was an error during DCV Connection Gateway installation" | tee -a "$LOG_PATH"
fi
