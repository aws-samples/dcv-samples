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

set -eE
LOG_PATH="/var/log/dcv-session-mgr-install.log"
echo $(date -u) "*****START USER DATA SCRIPT*****" | tee -a $LOG_PATH

# Retrieve System Info
read -r system version <<<$(echo $(cat /etc/os-release | grep "^ID=\|^VERSION_ID=" | sort | cut -d"=" -f2 | tr -d "\"" | tr '[:upper:]' '[:lower:]'))
major_version="${version%.*}"
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
    curl -o "$TMP_DIR/nice-dcv-session-manager-broker.$package_extension" "$CLOUDFRONT_PREFIX/nice-dcv-session-manager-broker_all.$package_type.$package_extension"
else
    rpm --import "$CLOUDFRONT_PREFIX"/NICE-GPG-KEY
    curl -o "$TMP_DIR/nice-dcv-session-manager-broker.$package_extension" "$CLOUDFRONT_PREFIX/nice-dcv-session-manager-broker-$package_type.noarch.$package_extension"
fi 

# Install Packages
for package_pattern in "nice-dcv-session-manager-broker.$package_extension"; do
    package_full_path=$(find "$TMP_DIR" -name "$package_pattern")
    "$package_manager" install -y "$package_full_path"
done

# Enable and start DCV Session Manager service
systemctl start dcv-session-manager-broker
systemctl enable dcv-session-manager-broker

# Configure DCV Session Manager
CONFIG_PATH="/etc/dcv-session-manager-broker/session-manager-broker.properties"
## Enable the gateway in config
sed -i '/^enable-gateway/s/=.*$/= true/' "$CONFIG_PATH"
## Uncomment the broker connector host and port in config
sed -i '/gateway-to-broker-connector-https-port/s/^#\s//g' "$CONFIG_PATH"
sed -i '/gateway-to-broker-connector-bind-host/s/^#\s//g' "$CONFIG_PATH"
## (Optional) Enable the broker to persist on DynamoDB in config
#sed -i '/^enable-persistence/s/=.*$/= true/' "$CONFIG_PATH"
### Uncomment database, region, Read Capacity Units(RCU), Write Capacity Units(WCU), and table name prefix in config
#sed -i '/persistence-db/s/^#\s//g' "$CONFIG_PATH"
#sed -i '/dynamodb-region/s/^#\s//g' "$CONFIG_PATH"
#sed -i '/dynamodb-table-rcu/s/^#\s//g' "$CONFIG_PATH"
#sed -i '/dynamodb-table-wcu/s/^#\s//g' "$CONFIG_PATH"
#sed -i '/dynamodb-table-name-prefix/s/^#\s//g' "$CONFIG_PATH"
#sed -i "/^dynamodb-region/s/=.*$/= $REGION/" "$CONFIG_PATH"

# Restart the broker service 
systemctl restart dcv-session-manager-broker.service

# Clean Up
rm -rf "$TMP_DIR"

# Get the private IP for connection gateway to use during configuration
echo $(date -u) "Retrieving private broker DNS..." | tee -a "$LOG_PATH"
TOKEN=`curl -X PUT "http://169.254.169.254/latest/api/token" -H "X-aws-ec2-metadata-token-ttl-seconds: 21600"`
MAC=`curl -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/network/interfaces/macs/`
PRIVATE_DNS=`curl -H "X-aws-ec2-metadata-token: $TOKEN" "http://169.254.169.254/latest/meta-data/network/interfaces/macs/${MAC}local-hostname"`
echo $(date -u) "Using private DNS $PRIVATE_DNS" | tee -a "$LOG_PATH"

# Get current region
REGION=$(curl -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/placement/region)
echo $(date -u) "Current Region: $REGION" | tee -a "$LOG_PATH"

# Store the private private DNS name in SSM Parameter Store
echo $(date -u) "Storing broker private DNS name in AWS SSM Parameter Store..." | tee -a "$LOG_PATH"
aws ssm put-parameter --name dcv-broker-private-dns --value "$PRIVATE_DNS" --type String --overwrite --region "$REGION"
# Log if successful installation
if [[ $? -eq 0 ]]; then
    echo $(date -u) "Stored private DNS name $PRIVATE_DNS in Parameter Store" | tee -a "$LOG_PATH"
else
    echo $(date -u) "There was an error during DCV Session Manager installation" | tee -a "$LOG_PATH"
fi