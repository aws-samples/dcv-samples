import json
import boto3
import os
from typing import Dict, Any

def handler(event: Dict[str, Any], context) -> Dict[str, Any]:
    """
    Lambda function to stop EC2 instance before AMI creation
    Only stops if explicitly requested via configuration or event parameter
    """
    ec2 = boto3.client('ec2')
    
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
        
        print(f"Processing stop request for instance: {instance_id}")
        
        # Check if stopping is requested
        ami_config = config.get('ami', {})
        ami_options = ami_config.get('options', {})
        
        # Priority: event parameter > config setting > default false
        stop_instance = event.get('stop_instance', 
                                 ami_options.get('stop_instance_before_creation', False))
        
        if not stop_instance:
            print(f"Instance stopping not requested - keeping instance {instance_id} running")
            # Get actual instance state
            try:
                response = ec2.describe_instances(InstanceIds=[instance_id])
                actual_state = response['Reservations'][0]['Instances'][0]['State']['Name']
            except (ec2.exceptions.ClientError, IndexError, KeyError) as e:
                print(f"Error getting instance state: {e}")
                actual_state = 'unknown'
            
            return {
                'statusCode': 200,
                'status': 'success',
                'instance_id': instance_id,
                'instance_state': actual_state,
                'action': 'skipped',
                'stop_requested': False,
                'message': f'Instance {instance_id} stopping not requested'
            }
        
        # Verify instance exists and get current state
        try:
            response = ec2.describe_instances(InstanceIds=[instance_id])
            instance = response['Reservations'][0]['Instances'][0]
            current_state = instance['State']['Name']
            
            if current_state == 'stopped':
                print(f"Instance {instance_id} is already stopped")
                return {
                    'statusCode': 200,
                    'status': 'success',
                    'instance_id': instance_id,
                    'instance_state': current_state,
                    'action': 'already_stopped',
                    'stop_requested': True,
                    'message': f'Instance {instance_id} was already stopped'
                }
            
            if current_state in ['stopping', 'terminated', 'terminating']:
                return {
                    'statusCode': 400,
                    'status': 'failed',
                    'error': f'Instance {instance_id} is in {current_state} state - cannot stop',
                    'instance_id': instance_id,
                    'instance_state': current_state,
                    'action': 'failed',
                    'stop_requested': True
                }
            
            if current_state != 'running':
                return {
                    'statusCode': 400,
                    'status': 'failed',
                    'error': f'Instance {instance_id} is in {current_state} state - cannot stop',
                    'instance_id': instance_id,
                    'instance_state': current_state,
                    'action': 'failed',
                    'stop_requested': True
                }
                
        except ec2.exceptions.ClientError as e:
            if 'InvalidInstanceID.NotFound' in str(e):
                return {
                    'statusCode': 404,
                    'status': 'failed',
                    'error': f'Instance {instance_id} not found',
                    'instance_id': instance_id,
                    'action': 'failed',
                    'stop_requested': True
                }
            return {
                'statusCode': 500,
                'status': 'failed',
                'error': f'Error describing instance: {str(e)}',
                'instance_id': instance_id,
                'action': 'failed',
                'stop_requested': True
            }
        
        # Perform the stop
        print(f"Stopping instance {instance_id} (current state: {current_state})")
        
        try:
            stop_response = ec2.stop_instances(InstanceIds=[instance_id])
            stopping_instance = stop_response['StoppingInstances'][0]
            new_state = stopping_instance['CurrentState']['Name']
        except ec2.exceptions.ClientError as e:
            return {
                'statusCode': 500,
                'status': 'failed',
                'error': f'Failed to stop instance: {str(e)}',
                'instance_id': instance_id,
                'instance_state': current_state,
                'action': 'failed',
                'stop_requested': True
            }
        
        print(f"Instance {instance_id} stop initiated - state changed to: {new_state}")
        
        return {
            'statusCode': 200,
            'status': 'success',
            'instance_id': instance_id,
            'instance_state': new_state,
            'previous_state': current_state,
            'action': 'stop_initiated',
            'stop_requested': True,
            'message': f'Instance {instance_id} stop initiated successfully'
        }
        
    except Exception as e:
        print(f"Error stopping instance: {str(e)}")
        return {
            'statusCode': 500,
            'status': 'failed',
            'error': str(e),
            'instance_id': event.get('instance_id', 'unknown'),
            'action': 'failed',
            'stop_requested': True,
            'message': 'Failed to stop instance'
        }
