import json
import boto3
import os
from typing import Dict, Any
import time

def handler(event: Dict[str, Any], context) -> Dict[str, Any]:
    """
    Lambda function to poll Mac SIP modification tasks
    This determines whether to proceed with AMI creation based on SIP status
    """
    
    try:
        # Load configuration from environment
        config_json = os.environ.get('CONFIG_JSON')
        if config_json:
            config = json.loads(config_json)
        else:
            raise ValueError("Configuration not found in environment variables")
        
        # Get Mac monitoring configuration
        mac_config = config['mac_monitoring']
        
        # Get instance ID from previous step
        instance_id = event.get('instance_id')
        if not instance_id:
            raise ValueError("No instance_id provided in event")
        
        print(f"Checking Mac SIP modification tasks for instance {instance_id}")
        
        # Initialize EC2 client
        ec2 = boto3.client('ec2')
        
        # Call describe_mac_modification_tasks API
        try:
            print(f"Calling describe_mac_modification_tasks without filters")
            
            response = ec2.describe_mac_modification_tasks(
                MaxResults=50
            )
            print(f"Response: {response}")
            all_tasks = response.get('MacModificationTasks', [])
            
            # Filter tasks by instance ID
            tasks = [task for task in all_tasks if task.get('InstanceId') == instance_id]
            
            # Apply additional filters if configured
            task_type = mac_config.get('task_filters', {}).get('task-type')
            if task_type:
                tasks = [task for task in tasks if task.get('TaskType') == task_type]
            
            task_states = mac_config.get('task_filters', {}).get('task-state', [])
            if task_states:
                task_states_list = task_states if isinstance(task_states, list) else [task_states]
                tasks = [task for task in tasks if task.get('TaskState') in task_states_list]
            # Get target SIP status from event or config (support both disabled and enabled)
            target_sip_status = event.get('target_sip_status', 'disabled')
            
            print(f"Found {len(tasks)} Mac modification tasks")
            
            if not tasks:
                # No tasks found - instance may still be initializing
                status = 'pending'
                proceed = False
                api_message = 'No Mac modification tasks found yet, instance may still be initializing'
                sip_status = 'unknown'
            else:
                # Check the most recent task
                latest_task = max(tasks, key=lambda x: x.get('StartTime', ''))
                task_state = latest_task.get('TaskState', 'unknown')
                
                print(f"Latest task state: {task_state}")
                
                if task_state == 'successful':
                    # Check SIP configuration
                    sip_config = latest_task.get('MacSystemIntegrityProtectionConfig', {})
                    sip_status = sip_config.get('Status', 'unknown')
                    
                    print(f"SIP Status: {sip_status}")
                    
                    if sip_status == target_sip_status:
                        # SIP is in the target state - proceed to next step
                        status = 'success'
                        proceed = True
                        api_message = f'Mac SIP status is {sip_status} - target state achieved'
                    else:
                        # SIP is not in target state yet
                        status = 'pending'
                        proceed = False
                        api_message = f'Mac SIP status is {sip_status}, waiting for {target_sip_status}'
                        
                elif task_state in ['in-progress', 'pending']:
                    # Task is still running
                    status = 'pending'
                    proceed = False
                    api_message = f'Mac modification task is {task_state}'
                    sip_status = 'in-progress'
                    
                elif task_state == 'failed':
                    # Task failed
                    status = 'failed'
                    proceed = False
                    api_message = f'Mac modification task failed'
                    sip_status = 'failed'
                    
                else:
                    # Unknown task state
                    status = 'pending'
                    proceed = False
                    api_message = f'Unknown task state: {task_state}'
                    sip_status = 'unknown'
            
            print(f"SIP check result: status={status}, proceed={proceed}, sip_status={sip_status}")
            
        except Exception as e:
            print(f"Error calling describe_mac_modification_tasks: {str(e)}")
            status = 'failed'
            proceed = False
            api_message = f"Failed to check Mac modification tasks: {str(e)}"
            sip_status = 'error'
        
        result = {
            'statusCode': 200,
            'status': status,
            'proceed': proceed,
            'instance_id': instance_id,
            'sip_status': sip_status,
            'api_response': api_message,
            'timestamp': int(time.time())
        }
        
        print(f"Mac SIP poller result: {json.dumps(result)}")
        return result
        
    except Exception as e:
        print(f"Error in Mac SIP poller: {str(e)}")
        return {
            'statusCode': 500,
            'status': 'failed',
            'proceed': False,
            'error': str(e),
            'instance_id': event.get('instance_id', 'unknown'),
            'sip_status': 'error',
            'message': 'Mac SIP polling failed'
        }