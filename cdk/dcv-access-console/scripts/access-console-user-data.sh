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

LOG_PATH="/var/log/dcv-access-console-install.log"
echo $(date -u) "*****START USER DATA SCRIPT*****" | tee -a "$LOG_PATH"
TMP_DIR="$(mktemp -d /tmp/XXXXXX)"
echo $(date -u) "Created temp directory: $TMP_DIR" | tee -a "$LOG_PATH"

# Uncommet the following two lines if launching an Ubuntu based AMI
#TMP_DIR="/etc/dcv-access-console-install"
#mkdir "$TMP_DIR"

# Retrieve System Info
read -r system version <<<$(echo $(cat /etc/os-release | grep "^ID=\|^VERSION_ID=" | sort | cut -d"=" -f2 | tr -d "\"" | tr '[:upper:]' '[:lower:]'))
major_version="${version%.*}"
arch="$(arch)"
CLOUDFRONT_PREFIX="https://d1uj6qtbmh3dt5.cloudfront.net"

case $system in
    amzn )
        if [ "$major_version" = 2023 ]; then
            package_type="el9"
            package_manager="yum"
            package_extension="rpm"
        elif [ "$major_version" = 2 ]; then
            package_type="el7"
            package_manager="yum"
            package_extension="rpm"
        fi
        ;;
    centos|rhel|rocky )
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
        echo $(date -u) "Error: system '$system' is not supported" | tee -a "$LOG_PATH"
        exit 1
        ;;
esac

if [ -z "$package_type" ]; then
    echo $(date -u) "Error: system '$system' with version '$version' is not supported for arch '$arch'" | tee -a "$LOG_PATH"
    exit 1
fi

echo $(date -u) "System Info detected:" | tee -a "$LOG_PATH"
echo $(date -u) "OS Type: $package_type" | tee -a "$LOG_PATH"
echo $(date -u) "Package Manager: $package_manager" | tee -a "$LOG_PATH"

if ! command -v jq &> /dev/null
then
    echo $(date -u) "jq dependency not found. Installing" | tee -a "$LOG_PATH"
    "$package_manager" install -y jq
fi

if ! command -v aws &> /dev/null
then
    echo $(date -u) "awscli dependency not found. Installing" | tee -a "$LOG_PATH"
    "$package_manager" install -y awscli
fi

# Download Packages
if [ "$package_manager" = apt ]; then
    curl -o "$TMP_DIR/NICE-GPG-KEY" "$CLOUDFRONT_PREFIX/NICE-GPG-KEY"
    gpg --import "$TMP_DIR/NICE-GPG-KEY"
    if [ $arch != "x86_64" ]; then
        curl -o "$TMP_DIR/nice-dcv-access-console.tgz" "$CLOUDFRONT_PREFIX/nice-dcv-access-console-$package_type-aarch64.tgz"
    else
        curl -o "$TMP_DIR/nice-dcv-access-console.tgz" "$CLOUDFRONT_PREFIX/nice-dcv-access-console-$package_type-x86_64.tgz"
    fi
else
    rpm --import "$CLOUDFRONT_PREFIX"/NICE-GPG-KEY
    curl -o "$TMP_DIR/nice-dcv-access-console.tgz" "$CLOUDFRONT_PREFIX/nice-dcv-access-console-$package_type-$arch.tgz"
fi 

echo $(date -u) "DCV Access Console packages downloaded" | tee -a "$LOG_PATH"

tar -xvzf "$TMP_DIR/nice-dcv-access-console.tgz" -C "$TMP_DIR"

# Retrieve required setup information
TOKEN=`curl -X PUT "http://169.254.169.254/latest/api/token" -H "X-aws-ec2-metadata-token-ttl-seconds: 21600"`
region=$(curl -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/placement/region)
metadata=$(curl -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/)
if grep -q "public-hostname" <<< "$metadata"; then
    acDns=$(curl -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/public-hostname)
else
    acDns=$(curl -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/local-hostname)
fi
smDns=$(aws ssm get-parameter --name dcv-session-manager-dns --region "$region" --with-decryption | grep -Po '"Value": "\K[^"]*')
adminUser=$(aws ssm get-parameter --name dcv-access-console-admin --region "$region" --with-decryption | grep -Po '"Value": "\K[^"]*')
response=$?
if [[ "$response" -ne 0 ]]; then
    echo $(date -u) "SSM Parameter for admin not found. Defaulting to ec2-user" | tee -a "$LOG_PATH"
    adminUser="ec2-user"
fi
dcvConnGwyCheck=true
dcvConnGwy=$(aws ssm get-parameter --name dcv-connection-gwy-dns --region "$region" --with-decryption | grep -Po '"Value": "\K[^"]*')
response=$?
if [[ "$response" -ne 0 ]]; then
    echo $(date -u) "SSM Parameter for DCV Connection Gateway not found. Disabling gateway in configuration." | tee -a "$LOG_PATH"
    dcvConnGwyCheck=false
fi
dbPwd=$(openssl rand -base64 12)
pamAuth="system-auth"
CREDS=$(aws ssm get-parameter --name dcv-session-manager-credentials --region "$region" --with-decryption | grep -Po '"Value": "\K[^"]*')
IFS=':'
read -r smClintId smClientPwd <<<"$CREDS"
echo $(date -u) "Configuration discovered:" | tee -a "$LOG_PATH"
echo $(date -u) "AWS Region: $region" | tee -a "$LOG_PATH"
echo $(date -u) "Access Console DNS: $acDns" | tee -a "$LOG_PATH"
echo $(date -u) "Broker DNS: $smDns" | tee -a "$LOG_PATH"
echo $(date -u) "DCV Connection Gateway DNS: $dcvConnGwy" | tee -a "$LOG_PATH"
echo $(date -u) "Admin User: $adminUser" | tee -a $"$LOG_PATH"

# Set configuration input
jsonPath=$(find "$TMP_DIR" | grep onebox_wizard_input.json)
basePath=$(dirname "$jsonPath")
json=$(cat "$jsonPath")
json=$(jq --arg acDns "$acDns" '."onebox-address" = $acDns' <<<"$json")
json=$(jq --arg smDns "$smDns" '."broker-address" = $smDns' <<<"$json")
json=$(jq --arg smClintId "$smClintId" '."broker-client-id" = $smClintId' <<<"$json")
json=$(jq --arg smClientPwd "$smClientPwd" '."broker-client-password" = $smClientPwd' <<<"$json")
json=$(jq -r '."mariadb-username"="maria"' <<<"$json")
json=$(jq --arg dbPwd "$dbPwd" '."mariadb-password" = $dbPwd' <<<"$json")
json=$(jq --arg adminUser "$adminUser" '."admin-user" = $adminUser' <<<"$json")
if [ $dcvConnGwyCheck ]; then
    json=$(jq -r '."enable-connection-gateway"=true' <<<"$json")
    json=$(jq --arg dcvConnGwy "$dcvConnGwy" '."connection-gateway-host" = $dcvConnGwy' <<<"$json")
fi
json=$(jq --arg pamAuth $pamAuth '. + {"pam-service-name": $pamAuth}' <<<"$json")
echo "$json" > "$basePath/onebox-config-input.json"

# Install packages
if [ "$system" = rocky ]; then
    sudo setsebool -P httpd_can_network_connect 1
fi
wizardPath=$(find "$TMP_DIR" | grep wizard.py)
cd $basePath
echo $(date -u) "Initiating DCV Access Console installation wizard" | tee -a "$LOG_PATH"

# Comment out the following command and run manually on Ubuntu
python3 wizard.py --is-onebox --input-json onebox-config-input.json --force

echo "$json" > /etc/dcv-access-console-auth-server/onebox-config-input-bak.json
echo $(date -u) "Created config backup at /etc/dcv-access-console-auth-server/onebox-config-input-bak.json" | tee -a "$LOG_PATH"
