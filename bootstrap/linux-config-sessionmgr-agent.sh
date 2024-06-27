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

BROKER_PRIVATE_DNS="SESSION-MGR-PRIVATE-DNS"
sed -i --expression "s|#auth-token-verifier=\"https://127.0.0.1:8444\"|auth-token-verifier=\"https://$BROKER_PRIVATE_DNS:8445/agent/validate-authentication-token\"|" /etc/dcv/dcv.conf
sed -i "/\[security\]/a administrators=[\"dcvsmagent\"]\nno-tls-strict=true" /etc/dcv/dcv.conf
sed -i --expression "s|broker_host = ''|broker_host = \"$BROKER_PRIVATE_DNS\"|" /etc/dcv-session-manager-agent/agent.conf
sed -i --expression 's|#tls_strict = false|tls_strict = false|' /etc/dcv-session-manager-agent/agent.conf
systemctl enable dcv-session-manager-agent.service
systemctl start dcv-session-manager-agent
systemctl restart dcvserver