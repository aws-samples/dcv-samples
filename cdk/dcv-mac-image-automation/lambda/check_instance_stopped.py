import json
import boto3
import os
from typing import Dict, Any

def handler(event: Dict[str, Any], context) -> Dict[str, Any]:
    """
    Lambda function to check if EC2 instance is stopped and ready for AMI creation
    Returns success when instance is stopped, pending while stopping, failed on error
    """
    ec2 = boto3.client('ec2')
    
    try:
        # Get instance ID from event
        instance_id = event.get('instance_id')
        if not instance_id:
            raise ValueError("No instance_id provided in event")
        
        # Check if stopping was requested (to determine if we should wait for stopped state)
        stop_requested = event.get('stop_requested', False)
        
        print(f"Checking instance status: {instance_id} (stop_requested: {stop_requested})")
        
        try:
            # Check instance status
            response = ec2.describe_instances(InstanceIds=[instance_id])
            
            if not response['Reservations'] or not response['Reservations'][0]['Instances']:
                return {
                    'statusCode': 404,
                    'status': 'failed',
                    'error': f'Instance {instance_id} not found',
                    'instance_id': instance_id,
                    'stop_requested': stop_requested
                }
            
            instance = response['Reservations'][0]['Instances'][0]
            instance_state = instance['State']['Name']
            
            print(f"Instance {instance_id} current state: {instance_state}")
            
            # If stopping was not requested, instance can be in any valid state for AMI creation
            if not stop_requested:
                if instance_state in ['running', 'stopped']:
                    return {
                        'statusCode': 200,
                        'status': 'success',
                        'instance_id': instance_id,
                        'instance_state': instance_state,
                        'stop_requested': False,
                        'message': f'Instance {instance_id} is in {instance_state} state and ready for AMI creation'
                    }
                else:
                    return {
                        'statusCode': 400,
                        'status': 'failed',
                        'error': f'Instance {instance_id} is in {instance_state} state - cannot create AMI',
                        'instance_id': instance_id,
                        'instance_state': instance_state,
                        'stop_requested': False
                    }
            
            # If stopping was requested, we need to wait for stopped state
            if instance_state == 'stopped':
                return {
                    'statusCode': 200,
                    'status': 'success',
                    'instance_id': instance_id,
                    'instance_state': instance_state,
                    'stop_requested': True,
                    'message': f'Instance {instance_id} is now stopped and ready for AMI creation'
                }
            elif instance_state == 'stopping':
                return {
                    'statusCode': 200,
                    'status': 'pending',
                    'instance_id': instance_id,
                    'instance_state': instance_state,
                    'stop_requested': True,
                    'message': f'Instance {instance_id} is still stopping'
                }
            elif instance_state in ['terminated', 'terminating']:
                return {
                    'statusCode': 400,
                    'status': 'failed',
                    'error': f'Instance {instance_id} is {instance_state} - cannot create AMI',
                    'instance_id': instance_id,
                    'instance_state': instance_state,
                    'stop_requested': True
                }
            else:
                # Instance went back to running or other state unexpectedly
                return {
                    'statusCode': 400,
                    'status': 'failed',
                    'error': f'Instance {instance_id} is in unexpected state {instance_state} after stop request',
                    'instance_id': instance_id,
                    'instance_state': instance_state,
                    'stop_requested': True
                }
                
        except ec2.exceptions.ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'InvalidInstanceID.NotFound':
                return {
                    'statusCode': 404,
                    'status': 'failed',
                    'error': f'Instance {instance_id} not found',
                    'instance_id': instance_id,
                    'stop_requested': stop_requested
                }
            else:
                raise
        
    except Exception as e:
        print(f"Error checking instance status: {str(e)}")
        return {
            'statusCode': 500,
            'status': 'failed',
            'error': str(e),
            'instance_id': event.get('instance_id', 'unknown'),
            'stop_requested': event.get('stop_requested', False),
            'message': 'Failed to check instance status'
        }
