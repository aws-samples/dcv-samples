# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import json
import boto3
from botocore.exceptions import ClientError

ec2 = boto3.client('ec2')

TCP_PORT = 8443
UDP_PORT = 8443

def get_instance_ip(instance_id):
    """ Given an instance ID this returns the private Ip address corresponding to it """
    try:
        response = ec2.describe_instances(InstanceIds=[instance_id])
        private_ip_addr = response['Reservations'][0]['Instances'][0]['PrivateIpAddress']
        return private_ip_addr
    except ClientError:
        return {
            'statusCode': 404,
            'body': f"Invalid session ID '{instance_id}'."
        }


# https://docs.aws.amazon.com/dcv/latest/gw-admin/session-resolver.html#implementing-session-resolver
def lambda_handler(event, context):
    # Gateway POST - sessionId=session_id&transport=transport&clientIpAddress=clientIpAddress
    session_id = event['queryStringParameters']['sessionId']
    transport = event['queryStringParameters']['transport']

    if session_id is None:
        return {
            'statusCode': 400,
            'body': "Missing sessionId parameter"
        }

    if transport not in ["HTTP", "QUIC"]:
        return {
            'statusCode': 400,
            'body': "Invalid transport parameter: " + transport
        }

    server_endpoint = get_instance_ip(session_id)
    port = int(TCP_PORT if transport == 'HTTP' else UDP_PORT)
    session_details = {
        'SessionId': "console",
        'DcvServerEndpoint': server_endpoint,
        'Port': port,
        'WebUrlPath': '/',
        'TransportProtocol':transport
    }
    if 'statusCode' in server_endpoint:
        return server_endpoint
    if 'statusCode' not in server_endpoint:
        return {
            'statusCode': 200,
            'body': json.dumps(session_details)
        }
