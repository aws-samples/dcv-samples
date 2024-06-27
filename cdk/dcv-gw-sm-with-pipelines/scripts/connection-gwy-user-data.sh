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