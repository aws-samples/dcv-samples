import json
import boto3
import os
from typing import Dict, Any

def handler(event: Dict[str, Any], context) -> Dict[str, Any]:
    """
    Lambda function to launch an EC2 instance with custom user data
    """
    ec2 = boto3.client('ec2')
    
    try:
        # Load configuration from environment
        config_json = os.environ.get('CONFIG_JSON')
        if config_json:
            config = json.loads(config_json)
        else:
            raise ValueError("Configuration not found in environment variables")
        
        # Get environment variables with error handling
        vpc_id = os.environ.get('VPC_ID')
        if not vpc_id:
            raise ValueError("VPC_ID environment variable is required")
        
        subnet_id = os.environ.get('SUBNET_ID')  # This is the private subnet in the target AZ
        if not subnet_id:
            raise ValueError("SUBNET_ID environment variable is required")
        
        security_group_id = os.environ.get('SECURITY_GROUP_ID')
        if not security_group_id:
            raise ValueError("SECURITY_GROUP_ID environment variable is required")
        
        instance_profile_arn = os.environ.get('INSTANCE_PROFILE_ARN')
        if not instance_profile_arn:
            raise ValueError("INSTANCE_PROFILE_ARN environment variable is required")
        
        # Extract instance profile name from ARN
        instance_profile_name = instance_profile_arn.split('/')[-1]
        
        # Get EC2 configuration with validation
        ec2_config = config.get('ec2')
        if not ec2_config:
            raise ValueError("EC2 configuration section missing from config")
        
        # Get password from config with validation
        ec2_user_password = ec2_config.get('ec2_user_password')
        if not ec2_user_password:
            raise ValueError("ec2_user_password is required in EC2 configuration")
        
        # User data script for Mac instance with SIP modification to disable SIP
        user_data_script = f"""#!/bin/bash
# Mac instance user data script for SIP modification
# This script initiates System Integrity Protection (SIP) modification

# Log startup
echo "Mac instance user data started at $(date)" > /var/log/mac-userdata.log

# Create log function
log_message() {{
    echo "$(date): $1" >> /var/log/mac-userdata.log
}}

# Set password for ec2-user (who initially has no password)
log_message "Setting password for ec2-user account"
log_message "Password: [REDACTED]"

# Verify ec2-user has admin privileges (required for secure token operations)
if dseditgroup -o checkmember -m ec2-user admin; then
    log_message "Confirmed ec2-user has admin privileges"
else
    log_message "Warning: ec2-user does not have admin privileges - adding to admin group"
    dseditgroup -o edit -a ec2-user -t user admin
fi

# First, set the password using dscl 
#dscl . -passwd /Users/ec2-user {ec2_user_password}
/usr/bin/dscl . -passwd /Users/ec2-user "{ec2_user_password}"
if [ $? -eq 0 ]; then
    log_message "Password successfully set for ec2-user using dscl"
    
    # Enable secure token for ec2-user (required for FileVault and MDM operations)
    # Use sysadminctl with the newly set password to enable secure token
    sudo -su ec2-user sysadminctl -newPassword "{ec2_user_password}" -oldPassword "{ec2_user_password}"
    #sleep 10
    #sysadminctl -secureTokenOn ec2-user -password {ec2_user_password} -adminUser ec2-user -adminPassword {ec2_user_password}
    if [ $? -eq 0 ]; then
        log_message "Secure token enabled for ec2-user"
    else
        log_message "Warning: Failed to enable secure token for ec2-user, but password was set successfully"
        # Alternative approach: try using interactive mode
        log_message "Attempting alternative secure token method"
        echo "{ec2_user_password}" | sysadminctl -secureTokenOn ec2-user -password - -adminUser ec2-user -adminPassword -
        if [ $? -eq 0 ]; then
            log_message "Secure token enabled using alternative method"
        else
            log_message "Unable to enable secure token - may need manual intervention"
        fi
    fi
else
    log_message "Error: Failed to set password for ec2-user"
    exit 1
fi

TOKEN=`curl -X PUT "http://169.254.169.254/latest/api/token" -H "X-aws-ec2-metadata-token-ttl-seconds: 21600"`
INSTANCE_ID=$(curl -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/instance-id)
log_message "Instance ID: $INSTANCE_ID"

log_message "Starting SIP modification process"

# Create credentials JSON string
CREDENTIALS_JSON='{{"rootVolumeUsername":"ec2-user","rootVolumePassword":"{ec2_user_password}"}}'
log_message "Credentials JSON prepared"

# Call AWS API with the credentials JSON
aws ec2 create-mac-system-integrity-protection-modification-task \
--instance-id "$INSTANCE_ID" \
--mac-credentials "$CREDENTIALS_JSON" \
--mac-system-integrity-protection-status "disabled"

# Store the exit code to check if the AWS command succeeded
AWS_EXIT_CODE=$?

log_message "SIP modification API call completed"

# Check if the AWS command was successful
if [ $AWS_EXIT_CODE -eq 0 ]; then
    log_message "SIP modification task created successfully"
else
    log_message "Error: Failed to create SIP modification task (exit code: $AWS_EXIT_CODE)"
    exit 1
fi

# Signal completion
echo "Mac user data script completed at $(date)" >> /var/log/mac-userdata.log
"""
        
        # Prepare run instances parameters
        run_instances_params = {
            'ImageId': ec2_config['ami_id'],
            'MinCount': 1,
            'MaxCount': 1,
            'InstanceType': ec2_config['instance_type'],
            'SecurityGroupIds': [security_group_id],
            'SubnetId': subnet_id,
            'UserData': user_data_script,
            'IamInstanceProfile': {
                'Name': instance_profile_name
            }
        }
        
        # Add placement configuration for Mac instances (dedicated host requirement)
        placement_config = ec2_config.get('placement', {})
        if placement_config:
            placement = {}
            
            # Set tenancy (required for Mac instances)
            tenancy = placement_config.get('tenancy', 'host')
            if tenancy:
                placement['Tenancy'] = tenancy
            
            # Set specific host ID if provided
            host_id = placement_config.get('host_id')
            if host_id:
                placement['HostId'] = host_id
            
            # Set availability zone if provided
            availability_zone = placement_config.get('availability_zone')
            if availability_zone:
                placement['AvailabilityZone'] = availability_zone
            
            if placement:
                run_instances_params['Placement'] = placement
                print(f"Using placement configuration: {placement}")
        
        # For Mac instances, ensure dedicated tenancy is set
        instance_type = ec2_config['instance_type']
        if instance_type.startswith('mac') and 'Placement' not in run_instances_params:
            run_instances_params['Placement'] = {'Tenancy': 'host'}
            print("Mac instance detected - setting default dedicated host tenancy")
        
        # Add key name if provided (either from config or event)
        key_name = event.get('key_name') or ec2_config.get('key_name')
        if key_name:
            run_instances_params['KeyName'] = key_name
        
        # Prepare tags from config and merge with any custom tags from event
        tags = []
        for key, value in ec2_config['tags'].items():
            tags.append({'Key': key, 'Value': value})
        
        # Add custom tags from event if provided
        custom_tags = event.get('custom_tags', {})
        for key, value in custom_tags.items():
            tags.append({'Key': key, 'Value': value})
        
        run_instances_params['TagSpecifications'] = [
            {
                'ResourceType': 'instance',
                'Tags': tags
            }
        ]
        
        # Launch EC2 instance
        response = ec2.run_instances(**run_instances_params)
        
        instance_id = response['Instances'][0]['InstanceId']
        
        # Wait for instance to be in running state
        waiter = ec2.get_waiter('instance_running')
        waiter.wait(
            InstanceIds=[instance_id],
            WaiterConfig={
                'Delay': 45,
                'MaxAttempts': 40
            }
        )
        
        print(f"Successfully launched EC2 instance: {instance_id}")
        
        # Get AMI options for workflow decisions
        ami_config = config.get('ami', {})
        ami_options = ami_config.get('options', {})
        
        # Get terminate_instance setting (can be overridden by event input)
        terminate_instance = event.get('terminate_instance', 
                                     ami_options.get('terminate_instance_after_creation', False))
        
        return {
            'statusCode': 200,
            'instance_id': instance_id,
            'state': 'running',
            'terminate_instance': terminate_instance,
            'message': f'EC2 instance {instance_id} launched successfully'
        }
        
    except Exception as e:
        print(f"Error launching EC2 instance: {str(e)}")
        return {
            'statusCode': 500,
            'error': str(e),
            'message': 'Failed to launch EC2 instance'
        }