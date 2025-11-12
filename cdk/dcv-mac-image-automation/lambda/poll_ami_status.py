import json
import boto3
import os
from typing import Dict, Any

def handler(event: Dict[str, Any], context) -> Dict[str, Any]:
    """
    Lambda function to poll AMI creation status
    Returns success when AMI is available, pending while in progress, failed on error
    """
    ec2 = boto3.client('ec2')
    
    try:
        # Get AMI ID from event
        ami_id = event.get('ami_id')
        if not ami_id:
            raise ValueError("No ami_id provided in event")
        
        # Get instance ID for context
        instance_id = event.get('instance_id')
        
        print(f"Checking AMI status: {ami_id} (from instance {instance_id})")
        
        try:
            # Check AMI status
            response = ec2.describe_images(ImageIds=[ami_id])
            
            if not response['Images']:
                return {
                    'statusCode': 404,
                    'status': 'failed',
                    'error': f'AMI {ami_id} not found',
                    'ami_id': ami_id,
                    'instance_id': instance_id
                }
            
            image = response['Images'][0]
            ami_state = image['State']
            
            print(f"AMI {ami_id} current state: {ami_state}")
            
            if ami_state == 'available':
                return {
                    'statusCode': 200,
                    'status': 'success',
                    'ami_id': ami_id,
                    'ami_state': ami_state,
                    'ami_name': image.get('Name', ''),
                    'instance_id': instance_id,
                    'message': f'AMI {ami_id} is now available'
                }
            elif ami_state == 'pending':
                return {
                    'statusCode': 200,
                    'status': 'pending',
                    'ami_id': ami_id,
                    'ami_state': ami_state,
                    'instance_id': instance_id,
                    'message': f'AMI {ami_id} is still being created'
                }
            elif ami_state == 'failed':
                # Get failure reason if available
                state_reason = image.get('StateReason', {})
                failure_reason = state_reason.get('Message', 'Unknown failure reason')
                
                return {
                    'statusCode': 400,
                    'status': 'failed',
                    'ami_id': ami_id,
                    'ami_state': ami_state,
                    'error': f'AMI creation failed: {failure_reason}',
                    'instance_id': instance_id,
                    'message': f'AMI {ami_id} creation failed'
                }
            else:
                # Handle other possible states (deregistered, etc.)
                return {
                    'statusCode': 400,
                    'status': 'failed',
                    'ami_id': ami_id,
                    'ami_state': ami_state,
                    'error': f'AMI in unexpected state: {ami_state}',
                    'instance_id': instance_id,
                    'message': f'AMI {ami_id} in unexpected state'
                }
                
        except ec2.exceptions.ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'InvalidAMIID.NotFound':
                return {
                    'statusCode': 404,
                    'status': 'failed',
                    'error': f'AMI {ami_id} not found',
                    'ami_id': ami_id,
                    'instance_id': instance_id
                }
            else:
                raise
        
    except Exception as e:
        print(f"Error checking AMI status: {str(e)}")
        return {
            'statusCode': 500,
            'status': 'failed',
            'error': str(e),
            'ami_id': event.get('ami_id', 'unknown'),
            'instance_id': event.get('instance_id', 'unknown'),
            'message': 'Failed to check AMI status'
        }
