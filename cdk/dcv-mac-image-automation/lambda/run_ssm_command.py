import json
import boto3
import os
from typing import Dict, Any
import time

def handler(event: Dict[str, Any], context) -> Dict[str, Any]:
    """
    Lambda function to run SSM RunCommand with retry logic
    Retries up to 5 times if command fails due to connectivity issues
    """
    
    try:
        # Load configuration from environment
        config_json = os.environ.get('CONFIG_JSON')
        if config_json:
            config = json.loads(config_json)
        else:
            raise ValueError("Configuration not found in environment variables")
        
        # Get instance ID from event
        instance_id = event.get('instance_id')
        if not instance_id:
            raise ValueError("No instance_id provided in event")
        
        # Get EC2 configuration
        ec2_config = config['ec2']
        
        # Get password from config
        ec2_user_password = ec2_config['ec2_user_password']
        
        # Get DCV server build location from config
        dcv_server_build_location = ec2_config['dcv_server_build_location']
        
        # Validate DCV server build location to prevent command injection
        automatic_dcv_session = str(ec2_config['automatic_ec2-user_dcv_session_creation']).lower()
        if not (dcv_server_build_location.startswith('https://') or dcv_server_build_location.startswith('s3://')):
                raise ValueError("Invalid DCV server build location: must start with https:// or s3://")
        if '"' in dcv_server_build_location or "'" in dcv_server_build_location or ';' in dcv_server_build_location or '`' in dcv_server_build_location or '$(' in dcv_server_build_location:
            raise ValueError("Invalid characters in DCV server build location")
    
        # Get DCV session creation setting - validate to prevent injection
        automatic_dcv_session_raw = ec2_config['automatic_ec2-user_dcv_session_creation']
        if not isinstance(automatic_dcv_session_raw, bool):
            raise ValueError("automatic_ec2-user_dcv_session_creation must be a boolean")
        automatic_dcv_session = 'true' if automatic_dcv_session_raw else 'false'

        # Validate password doesn't contain shell metacharacters
        if any(char in ec2_user_password for char in ['"', "'", '`', '$', '\\', ';', '|', '&', '\n', '\r']):
            raise ValueError("Password contains invalid characters")
        
        # Get retry count from event (for retry logic)
        retry_count = event.get('ssm_retry_count', 0)
        max_retries = config.get('ssm', {}).get('max_retries', 5)
        
        # Check if we have an existing command_id to check status
        existing_command_id = event.get('command_id')
        
        if existing_command_id:
            print(f"Checking status of existing SSM command {existing_command_id} on instance {instance_id}")
        else:
            print(f"Running new SSM command on instance {instance_id} (attempt {retry_count + 1}/{max_retries + 1})")
        
        # Initialize SSM client
        ssm = boto3.client('ssm')
        
        # Get SSM command configuration
        ssm_config = config.get('ssm', {})
        working_directory = ssm_config.get('working_directory', '/tmp')
        timeout_seconds = ssm_config.get('timeout_seconds', 300)
        
        # Static script for DCV server installation and configuration with SIP modification to enable SIP
        command = f'''#!/bin/bash

set -eE

CLOUDFRONT_PREFIX="https://d1uj6qtbmh3dt5.cloudfront.net"

# Create temporary directory
TMP_DIR="$(mktemp -d /tmp/XXXXXX)"
trap 'rm -rf -- "$TMP_DIR"' ERR

# Get system information
os_version=$(sw_vers -productVersion)
system=$(system_profiler SPSoftwareDataType)
sip_status=$(echo "$system" | grep "System Integrity Protection" | awk -F': ' '{{print $2}}')

if [ "$sip_status" = "Enabled" ]; then
    echo "System Integrity Protection is enabled, please disable it first"
    exit 1
fi

# Check if OS version starts with 13, 14, or 15
case "$os_version" in
    13*|14*|15*)
        echo "OS version $os_version is supported"
        ;;
    *)
        echo "Unsupported OS version: $os_version. This script supports macOS 13, 14, and 15 only."
        exit 1
        ;;
esac

# Download DCV server build - dynamically handle S3 URI or HTTPS URL
if [[ "{dcv_server_build_location}" == s3://* ]]; then
    echo "Downloading DCV server build from S3: {dcv_server_build_location}"
    /opt/homebrew/bin/aws s3 cp "{dcv_server_build_location}" "$TMP_DIR/nice-dcv-server-macos-arm64.dist.pkg"
    DCV_DOWNLOAD_EXIT_CODE=$?
    DOWNLOAD_METHOD="S3"
else
    echo "Downloading DCV server build from HTTPS: {dcv_server_build_location}"
    curl -L -o "$TMP_DIR/nice-dcv-server-macos-arm64.dist.pkg" "{dcv_server_build_location}"
    DCV_DOWNLOAD_EXIT_CODE=$?
    DOWNLOAD_METHOD="HTTPS"
fi

if [ $DCV_DOWNLOAD_EXIT_CODE -eq 0 ]; then
    echo "DCV server build downloaded successfully via $DOWNLOAD_METHOD"
else
    echo "Error: Failed to download DCV server build via $DOWNLOAD_METHOD (exit code: $DCV_DOWNLOAD_EXIT_CODE)"
    exit 1
fi

installer -pkg "$TMP_DIR/nice-dcv-server-macos-arm64.dist.pkg" -target /

# Clean up
rm -rf -- "$TMP_DIR"

if [ "{automatic_dcv_session}" = "true" ]; then
    # Create DCV session
    echo "Configuring automatic DCV console creation for ec2-user"
    sed -i --expression 's|#create-session = true|create-session = true|' /etc/dcv/dcv.conf
    sed -i --expression 's|#owner = ""|owner = "ec2-user"|' /etc/dcv/dcv.conf
else
    echo "Automatic DCV console creation for ec2-user is disabled"
fi


TOKEN=`curl -X PUT "http://169.254.169.254/latest/api/token" -H "X-aws-ec2-metadata-token-ttl-seconds: 21600"`
INSTANCE_ID=$(curl -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/instance-id)
echo "Instance ID: $INSTANCE_ID"

echo "Starting SIP modification process"

# Create credentials JSON string
CREDENTIALS_JSON='{{"rootVolumeUsername":"ec2-user","rootVolumePassword":"{ec2_user_password}"}}'
echo "Credentials JSON prepared"

# Call AWS API with the credentials JSON
/opt/homebrew/bin/aws ec2 create-mac-system-integrity-protection-modification-task \
--instance-id "$INSTANCE_ID" \
--mac-credentials "$CREDENTIALS_JSON" \
--mac-system-integrity-protection-status "enabled"

# Store the exit code to check if the AWS command succeeded
AWS_SIP_EXIT_CODE=$?

echo "SIP modification API call completed"

# Check if the AWS command was successful
if [ $AWS_SIP_EXIT_CODE -eq 0 ]; then
    echo "SIP modification task created successfully"
else
    echo "Error: Failed to create SIP modification task (exit code: $AWS_SIP_EXIT_CODE)"
    exit 1
fi
'''
        
        try:
            if existing_command_id:
                # Check status of existing command
                command_id = existing_command_id
                print(f"Checking status of existing SSM command: {command_id}")
                
                # Check command status
                invocation_response = ssm.get_command_invocation(
                    CommandId=command_id,
                    InstanceId=instance_id
                )
            else:
                # Send new SSM RunCommand
                response = ssm.send_command(
                    InstanceIds=[instance_id],
                    DocumentName='AWS-RunShellScript',
                    Parameters={
                        'commands': [command],
                        'workingDirectory': [working_directory],
                        'executionTimeout': [str(timeout_seconds)]
                    },
                    TimeoutSeconds=timeout_seconds,
                    Comment=f'SIP enablement script execution - attempt {retry_count + 1}'
                )
                
                command_id = response['Command']['CommandId']
                print(f"New SSM command sent with ID: {command_id}")
                
                # Wait a moment for command to start
                time.sleep(5)
                
                # Check command status
                invocation_response = ssm.get_command_invocation(
                    CommandId=command_id,
                    InstanceId=instance_id
                )
            
            command_status = invocation_response.get('Status', 'Unknown')
            stdout = invocation_response.get('StandardOutputContent', '')
            stderr = invocation_response.get('StandardErrorContent', '')
            
            print(f"SSM command status: {command_status}")
            if stdout:
                print(f"Command output: {stdout}")
            if stderr:
                print(f"Command errors: {stderr}")
            
            # Handle different command statuses
            if command_status == 'Success':
                status = 'success'
                proceed = True
                message = 'SSM command executed successfully'
                retry_needed = False
                
            elif command_status in ['InProgress', 'Pending', 'Delayed']:
                status = 'pending' 
                proceed = False
                message = f'SSM command is {command_status}'
                retry_needed = False
                
            elif command_status in ['Failed', 'Cancelled', 'TimedOut']:
                # Check if this is a connectivity issue that should be retried
                is_connectivity_issue = (
                    'AccessDenied' in stderr or
                    'InvalidInstanceId' in stderr or
                    'connection' in stderr.lower() or
                    'network' in stderr.lower() or
                    command_status == 'TimedOut'
                )
                
                if is_connectivity_issue and retry_count < max_retries:
                    status = 'retry'
                    proceed = False
                    message = f'SSM command failed due to connectivity (attempt {retry_count + 1}/{max_retries + 1}), retrying'
                    retry_needed = True
                else:
                    status = 'failed'
                    proceed = False
                    message = f'SSM command failed: {command_status}. Output: {stderr}'
                    retry_needed = False
                    
            else:
                # Unknown status
                if retry_count < max_retries:
                    status = 'retry'
                    proceed = False
                    message = f'Unknown SSM command status: {command_status}, retrying'
                    retry_needed = True
                else:
                    status = 'failed'
                    proceed = False
                    message = f'Unknown SSM command status: {command_status}, max retries exceeded'
                    retry_needed = False
            
            result = {
                'statusCode': 200,
                'status': status,
                'proceed': proceed,
                'retry_needed': retry_needed,
                'instance_id': instance_id,
                'command_id': command_id,
                'command_status': command_status,
                'ssm_retry_count': retry_count + 1 if retry_needed else retry_count,
                'message': message,
                'stdout': stdout,
                'stderr': stderr,
                'timestamp': int(time.time())
            }
            
        except Exception as e:
            error_str = str(e)
            print(f"Error executing SSM command: {error_str}")
            
            # Check if this is a connectivity/access issue that should be retried
            is_connectivity_issue = (
                'InvalidInstanceId' in error_str or
                'AccessDenied' in error_str or
                'ThrottlingException' in error_str or
                'connection' in error_str.lower() or
                'network' in error_str.lower()
            )
            
            if is_connectivity_issue and retry_count < max_retries:
                status = 'retry'
                proceed = False
                message = f'SSM command failed due to connectivity error (attempt {retry_count + 1}/{max_retries + 1}), retrying: {error_str}'
                retry_needed = True
                command_id = None
                command_status = 'Error'
            else:
                status = 'failed'
                proceed = False
                message = f'SSM command failed: {error_str}'
                retry_needed = False
                command_id = None
                command_status = 'Error'
            
            result = {
                'statusCode': 200,
                'status': status,
                'proceed': proceed,
                'retry_needed': retry_needed,
                'instance_id': instance_id,
                'command_id': command_id,
                'command_status': command_status,
                'ssm_retry_count': retry_count + 1 if retry_needed else retry_count,
                'message': message,
                'error': error_str,
                'timestamp': int(time.time())
            }
        
        print(f"SSM command result: {json.dumps(result)}")
        return result
        
    except Exception as e:
        print(f"Error in SSM command runner: {str(e)}")
        return {
            'statusCode': 500,
            'status': 'failed',
            'proceed': False,
            'retry_needed': False,
            'error': str(e),
            'instance_id': event.get('instance_id', 'unknown'),
            'message': 'SSM command execution failed'
        }
