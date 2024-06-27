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

LOG_PATH="/var/log/dcv-session-mgr-install.log"
echo $(date -u) "*****START USER DATA SCRIPT*****" | tee -a "$LOG_PATH"

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
    # Restart the broker service for the new config to get pulled
    systemctl restart dcv-session-manager-broker.service
    echo $(date -u) "Successfully installed DCV Session Manager" | tee -a "$LOG_PATH"
else
    echo $(date -u) "There was an error during DCV Session Manager installation" | tee -a "$LOG_PATH"
fi