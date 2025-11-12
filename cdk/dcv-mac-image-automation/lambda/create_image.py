import json
import boto3
import os
from typing import Dict, Any
from datetime import datetime

def handler(event: Dict[str, Any], context) -> Dict[str, Any]:
    """
    Lambda function to create an AMI from the specified EC2 instance
    """
    ec2 = boto3.client('ec2')
    
    try:
        # Load configuration from environment
        config_json = os.environ.get('CONFIG_JSON')
        if config_json:
            try:
                config = json.loads(config_json)
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON in CONFIG_JSON environment variable: {e}")
        else:
            raise ValueError("Configuration not found in environment variables")
        
        # Get AMI configuration with validation
        ami_config = config.get('ami')
        if not ami_config:
            raise ValueError("AMI configuration section missing from config")
        
        # Get instance ID from previous step
        instance_id = event.get('instance_id')
        if not instance_id:
            raise ValueError("No instance_id provided in event")
        
        print(f"Creating AMI for instance: {instance_id}")
        
        # Verify instance exists and get its details
        try:
            instance_response = ec2.describe_instances(InstanceIds=[instance_id])
            reservations = instance_response.get('Reservations', [])
            if not reservations or not reservations[0].get('Instances'):
                raise ValueError(f"No instance data found for {instance_id}")
            instance = reservations[0]['Instances'][0]
            instance_state = instance['State']['Name']
            
            if instance_state not in ['running', 'stopped']:
                return {
                    'statusCode': 400,
                    'error': f'Instance {instance_id} is in {instance_state} state. Cannot create AMI.',
                    'instance_id': instance_id
                }
                
        except ec2.exceptions.ClientError as e:
            if 'InvalidInstanceID.NotFound' in str(e):
                return {
                    'statusCode': 404,
                    'error': f'Instance {instance_id} not found',
                    'instance_id': instance_id
                }
            raise
        
        # Generate AMI name and description using config patterns
        timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
        ami_name = ami_config['naming_pattern'].format(
            instance_id=instance_id,
            timestamp=timestamp
        )
        ami_description = ami_config['description_pattern'].format(
            instance_id=instance_id,
            timestamp=timestamp
        )
        
        # Prepare tags from config
        tags = []
        for key, value in ami_config.get('tags', {}).items():
            tags.append({'Key': key, 'Value': value})
        
        # Add standard tags
        tags.extend([
            {'Key': 'Name', 'Value': ami_name},
            {'Key': 'SourceInstance', 'Value': instance_id},
            {'Key': 'CreationDate', 'Value': timestamp}
        ])
        
        # Add custom tags from event if provided
        custom_tags = event.get('custom_ami_tags', {})
        for key, value in custom_tags.items():
            tags.append({'Key': key, 'Value': value})
        
        # Create AMI
        print(f"Creating AMI: {ami_name}")
        ami_response = ec2.create_image(
            InstanceId=instance_id,
            Name=ami_name,
            Description=ami_description,
            NoReboot=ami_config.get('no_reboot', True),
            TagSpecifications=[
                {
                    'ResourceType': 'image',
                    'Tags': tags
                }
            ]
        )
        
        ami_id = ami_response['ImageId']
        
        print(f"AMI creation initiated: {ami_id}")
        
        # Return immediately - AMI polling and instance termination are handled by separate Lambda functions
        ami_state = 'pending'
        
        # Get terminate_instance setting for Step Function decision
        ami_options = ami_config.get('options', {})
        terminate_instance = event.get('terminate_instance', 
                                     ami_options.get('terminate_instance_after_creation', False))
        
        result = {
            'statusCode': 200,
            'status': 'success',
            'ami_id': ami_id,
            'ami_name': ami_name,
            'ami_state': ami_state,
            'instance_id': instance_id,
            'creation_time': timestamp,
            'terminate_instance': terminate_instance,
            'message': f'AMI creation initiated successfully'
        }
        
        print(f"AMI creation result: {json.dumps(result)}")
        return result
        
    except Exception as e:
        print(f"Error creating AMI: {str(e)}")
        return {
            'statusCode': 500,
            'error': str(e),
            'instance_id': event.get('instance_id', 'unknown'),
            'message': 'Failed to create AMI'
        }