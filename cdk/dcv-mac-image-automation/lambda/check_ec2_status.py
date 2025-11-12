import json
import boto3
import os
from typing import Dict, Any
import time

def handler(event: Dict[str, Any], context) -> Dict[str, Any]:
    """
    Lambda function to check EC2 instance status checks
    Returns success when both system and instance status checks are passing
    """
    
    try:
        # Get instance ID from event
        instance_id = event.get('instance_id')
        if not instance_id:
            raise ValueError("No instance_id provided in event")
        
        print(f"Checking EC2 status checks for instance {instance_id}")
        
        # Initialize EC2 client
        ec2 = boto3.client('ec2')
        
        # Check instance status
        try:
            # Initialize status variables
            system_status = 'unknown'
            instance_status = 'unknown'
            
            response = ec2.describe_instance_status(
                InstanceIds=[instance_id],
                IncludeAllInstances=True
            )
            
            instance_statuses = response.get('InstanceStatuses', [])
            if not instance_statuses:
                # No status information available yet
                status = 'pending'
                proceed = False
                message = 'Instance status information not available yet'
            else:
                instance_status_info = instance_statuses[0]
                
                # Get system and instance status
                system_status = instance_status_info.get('SystemStatus', {}).get('Status', 'unknown')
                instance_status = instance_status_info.get('InstanceStatus', {}).get('Status', 'unknown')
                instance_state = instance_status_info.get('InstanceState', {}).get('Name', 'unknown')
                
                print(f"Instance state: {instance_state}")
                print(f"System status: {system_status}")
                print(f"Instance status: {instance_status}")
                
                # Check if instance is running and status checks are passing
                if instance_state == 'running' and system_status == 'ok' and instance_status == 'ok':
                    status = 'success'
                    proceed = True
                    message = 'All EC2 status checks are passing'
                elif instance_state != 'running':
                    status = 'pending'
                    proceed = False
                    message = f'Instance is {instance_state}, waiting for running state'
                else:
                    status = 'pending'
                    proceed = False
                    message = f'Status checks pending - System: {system_status}, Instance: {instance_status}'
            
            print(f"EC2 status check result: status={status}, proceed={proceed}")
            
        except Exception as e:
            print(f"Error checking instance status: {str(e)}")
            status = 'failed'
            proceed = False
            message = f"Failed to check instance status: {str(e)}"
            system_status = 'error'
            instance_status = 'error'
        
        result = {
            'statusCode': 200,
            'status': status,
            'proceed': proceed,
            'instance_id': instance_id,
            'system_status': system_status,
            'instance_status': instance_status,
            'message': message,
            'timestamp': int(time.time())
        }
        
        print(f"EC2 status check result: {json.dumps(result)}")
        return result
        
    except Exception as e:
        print(f"Error in EC2 status checker: {str(e)}")
        return {
            'statusCode': 500,
            'status': 'failed',
            'proceed': False,
            'error': str(e),
            'instance_id': event.get('instance_id', 'unknown'),
            'message': 'EC2 status check failed'
        }
