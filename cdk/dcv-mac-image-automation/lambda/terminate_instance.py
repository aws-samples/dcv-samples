import json
import boto3
import os
from typing import Dict, Any

def handler(event: Dict[str, Any], context) -> Dict[str, Any]:
    """
    Lambda function to terminate EC2 instance after AMI creation is complete
    Only terminates if explicitly requested via configuration or event parameter
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
        
        # Get AMI ID for context
        ami_id = event.get('ami_id', 'unknown')
        
        print(f"Processing termination request for instance: {instance_id} (AMI: {ami_id})")
        
        # Check if termination is requested
        ami_config = config.get('ami', {})
        ami_options = ami_config.get('options', {})
        
        # Priority: event parameter > config setting > default false
        terminate_instance = event.get('terminate_instance', 
                                     ami_options.get('terminate_instance_after_creation', False))
        
        if not terminate_instance:
            print(f"Instance termination not requested - keeping instance {instance_id} running")
            # Get actual instance state
            try:
                response = ec2.describe_instances(InstanceIds=[instance_id])
                actual_state = response['Reservations'][0]['Instances'][0]['State']['Name']
            except Exception as e:
                print(f"Error getting instance state, setting state to unknown: {e}")
                actual_state = 'unknown'
            
            return {
                'statusCode': 200,
                'status': 'success',
                'instance_id': instance_id,
                'instance_state': actual_state,
                'ami_id': ami_id,
                'action': 'skipped',
                'terminate_requested': False,
                'message': f'Instance {instance_id} kept running (termination not requested)'
            }
        
        # Verify instance exists and get current state
        try:
            response = ec2.describe_instances(InstanceIds=[instance_id])
            instance = response['Reservations'][0]['Instances'][0]
            current_state = instance['State']['Name']
            
            if current_state in ['terminated', 'terminating']:
                print(f"Instance {instance_id} is already {current_state}")
                return {
                    'statusCode': 200,
                    'status': 'success',
                    'instance_id': instance_id,
                    'instance_state': current_state,
                    'ami_id': ami_id,
                    'action': 'already_terminated',
                    'terminate_requested': True,
                    'message': f'Instance {instance_id} was already {current_state}'
                }
            
            if current_state not in ['running', 'stopped', 'stopping']:
                return {
                    'statusCode': 400,
                    'status': 'failed',
                    'error': f'Instance {instance_id} is in {current_state} state - cannot terminate',
                    'instance_id': instance_id,
                    'instance_state': current_state,
                    'ami_id': ami_id,
                    'action': 'failed',
                    'terminate_requested': True
                }
                
        except ec2.exceptions.ClientError as e:
            if 'InvalidInstanceID.NotFound' in str(e):
                return {
                    'statusCode': 404,
                    'status': 'failed',
                    'error': f'Instance {instance_id} not found',
                    'instance_id': instance_id,
                    'ami_id': ami_id,
                    'action': 'failed',
                    'terminate_requested': True
                }
            raise
        
        # Perform the termination
        print(f"Terminating instance {instance_id} (current state: {current_state})")
        
        terminate_response = ec2.terminate_instances(InstanceIds=[instance_id])
        terminating_instance = terminate_response['TerminatingInstances'][0]
        new_state = terminating_instance['CurrentState']['Name']
        
        print(f"Instance {instance_id} termination initiated - state changed to: {new_state}")
        
        return {
            'statusCode': 200,
            'status': 'success',
            'instance_id': instance_id,
            'instance_state': new_state,
            'previous_state': current_state,
            'ami_id': ami_id,
            'action': 'termination_initiated',
            'terminate_requested': True,
            'message': f'Instance {instance_id} termination initiated successfully'
        }
        
    except Exception as e:
        print(f"Error terminating instance: {str(e)}")
        return {
            'statusCode': 500,
            'status': 'failed',
            'error': str(e),
            'instance_id': event.get('instance_id', 'unknown'),
            'ami_id': event.get('ami_id', 'unknown'),
            'action': 'failed',
            'terminate_requested': True,
            'message': 'Failed to terminate instance'
        }
