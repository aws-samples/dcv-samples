# AWS EC2 Mac DCV Image Automation with Step Functions

This AWS CDK Python project creates an automated workflow using Step Functions to:

1. **Launch an EC2 Mac instance** and SIP modification to disable SIP
2. **Poll Mac SIP modification tasks** to wait for SIP status to become "disabled"
3. **Run SSM commands** to install and configure DCV server on the Mac instance and SIP modification to enable SIP
4. **Poll Mac SIP modification tasks** to wait for SIP status to become "enabled" again
5. **Create an AMI** with DCV server pre-installed and configured

**Mac DCV-Specific Automation**
Purpose-built for EC2 Mac instances with Amazon DCV server installation and System Integrity Protection (SIP) modification workflows.

**Configuration-Driven Approach**
All parameters are centralized in `config.json`.

## Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  Launch EC2     │───▶│  Wait & Poll    │───▶│  Run SSM        │───▶│  Poll SIP       │───▶│  Stop Instance  │
│  Mac Instance   │    │  SIP Disabled   │    │  Commands       │    │  Enabled        │    │  (Optional)     │
└─────────────────┘    └─────────────────┘    └─────────────────┘    └─────────────────┘    └─────────────────┘
                                                                                                        │
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐                                       │
│  Terminate      │◀───│  Poll AMI       │◀───│  Create AMI     │◀──────────────────────────────────────┘
│  Instance       │    │  Status         │    │  with DCV       │
│  (Optional)     │    │  (Optional)     │    │                 │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

**Workflow Details:**
- Launches EC2 Mac instance with SIP modification user data and DCV configuration
- Polls `describe_mac_modification_tasks` API every 8 minutes waiting for SIP to be disabled
- Runs SSM commands to install and configure Amazon DCV server on the Mac instance
- Polls for SIP status to become "enabled" again after DCV installation
- Optionally stops the instance before AMI creation (configurable)
- Creates AMI of the Mac instance with DCV server installed and configured
- Optionally waits for AMI creation to complete using non-blocking Step Function polling
- Optionally terminates the source instance after AMI creation (configurable)

## Components

### AWS Resources Created
- **VPC** with public/private subnets (configurable CIDR)
- **Security Group** for EC2 instances (configurable rules)
- **IAM Roles** for Lambda and EC2 with appropriate permissions
- **Lambda Functions** for each step of the automation
- **Step Function** to orchestrate the workflow
- **CloudWatch Logs** for monitoring

### Lambda Functions

1. **`launch_ec2.py`** - Launches EC2 Mac instance with SIP modification user data and DCV server configuration
2. **`api_poller.py`** - Polls Mac SIP modification tasks using `describe_mac_modification_tasks` API
3. **`check_ec2_status.py`** - Checks EC2 instance status and readiness for SSM commands
4. **`run_ssm_command.py`** - Runs SSM commands to install and configure Amazon DCV server
5. **`create_image.py`** - Creates AMI from the Mac instance with DCV server installed
6. **`stop_instance.py`** - Stops EC2 instance before AMI creation (optional, non-blocking)
7. **`check_instance_stopped.py`** - Polls instance status to verify it's stopped
8. **`poll_ami_status.py`** - Polls AMI creation status until available (non-blocking)
9. **`terminate_instance.py`** - Terminates source instance after AMI creation (optional)

### Configuration System

- **`config.json`** - Central configuration file for all parameters
- **`automation/config_loader.py`** - Configuration loading and validation
- **`validate_config.py`** - Configuration validation tool

## Prerequisites

1. **AWS CLI** configured with appropriate credentials
2. **AWS CDK** installed (`npm install -g aws-cdk`)
3. **Python 3.11+** 
4. **Virtual environment** (recommended)

## Setup and Deployment

### 1. Configure the Automation

First, customize the `config.json` file for your environment:

```bash
# Validate your configuration
python3 validate_config.py

# View configuration options
python3 validate_config.py template
```

### 2. Quick Deployment

Use the automated deployment script:

```bash
# This will install dependencies, validate config, and deploy
./deploy.sh
```

### 3. Manual Deployment (Alternative)

```bash
# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install Python dependencies
pip install -r requirements.txt

# Install Lambda dependencies
cd lambda
pip install -r requirements.txt -t .
cd ..

# Validate configuration
python3 validate_config.py

# Bootstrap CDK (first time only)
cdk bootstrap

# Deploy the stack
cdk deploy
```

## Configuration

### Key Configuration Sections

#### EC2 Configuration
```json
{
  "ec2": {
    "ami_id": "ami-0abcdef1234567890",
    "dcv_server_build_location": "https://d1uj6qtbmh3dt5.cloudfront.net/nice-dcv-server-macos-arm64.dist.pkg",
    "instance_type": "mac2-m2pro.metal",
    "key_name": "KeyPairPlaceholder",
    "ec2_user_password": "SecurePasswd12!",
    "automatic_ec2-user_dcv_session_creation": true,
    "placement": {
      "tenancy": "host",
      "host_id": "h-XXXXXXXXXXX",
      "availability_zone": "xx-xxxx-xx"
    },
    "tags": {
      "Name": "DCVMacAutomationInstance",
      "Purpose": "DCV-Mac-Automated-Image-Creation",
      "CreatedBy": "StepFunction",
      "Environment": "Development"
    },
    "security_group": {
      "ssh_access": false,
      "ssh_cidr": "0.0.0.0/0",
      "additional_ports": []
    }
  }, ...
}
```

**Note**: 
- The latest public AMI ID for EC2 Mac can be found in the EC2 AMI Catalog or SSM Parameter Store.
- User data script is embedded in the Lambda function code and includes DCV server installation
- Mac instances require dedicated host tenancy and optionally a specific host ID
- DCV server package supports both HTTPS URLs (CloudFront/web) and S3 URIs for flexible deployment
- When using S3 URIs, appropriate IAM permissions are automatically added to the EC2 instance

**DCV Server Build Location Options:**

The `dcv_server_build_location` parameter supports two formats:

1. **HTTPS URL** (recommended for public builds):
   ```json
   "dcv_server_build_location": "https://d1uj6qtbmh3dt5.cloudfront.net/nice-dcv-server-macos-arm64.dist.pkg"
   ```
   - Downloads using `curl` with redirect following (`-L` flag)
   - No additional IAM permissions required
   - Works with CloudFront, direct HTTPS URLs, etc.

2. **S3 URI** (for private/internal builds):
   ```json
   "dcv_server_build_location": "s3://my-private-bucket/builds/nice-dcv-server-macos-arm64.dist.pkg"
   ```
   - Downloads using AWS CLI (`aws s3 cp`)
   - Automatically adds S3 GetObject permissions to EC2 instance role
   - Supports private S3 buckets with proper IAM controls

#### Mac SIP Monitoring Configuration  
```json
{
  "mac_monitoring": {
    "polling_interval_minutes": 5,
    "max_polling_attempts": 60,
    "task_filters": {
      "task-type": "sip-modification",
      "task-state": ["successful", "failed", "in-progress", "pending"]
    },
    "timeout_hours": 5
  }
}
```

#### AMI Configuration
```json
{
  "ami": {
    "naming_pattern": "dcv-mac-automation-ami-{instance_id}-{timestamp}",
    "description_pattern": "DCV Mac Automated AMI created from instance {instance_id} on {timestamp}",
    "no_reboot": true,
    "tags": {
      "CreatedBy": "DCVMacAutomationStepFunction",
      "Purpose": "DCVMacAutomatedImageCreation"
    },
    "options": {
      "stop_instance_before_creation": false,
      "wait_for_completion": false,
      "terminate_instance_after_creation": false
    }
  }
}
```

#### SSM Configuration
```json
{
  "ssm": {
    "working_directory": "/tmp",
    "timeout_seconds": 300,
    "max_retries": 5
  }
}
```

### Configuration Validation

```bash
# Validate your configuration
python3 validate_config.py

# See all configuration options
python3 validate_config.py template
```

### Runtime Parameter Overrides

You can override config values at execution time using the same structure as config.json:

```json
{
  "ec2": {
    "key_name": "your-ec2-key-pair",
    "tags": {
      "Project": "MyProject",
      "Environment": "Production"
    }
  },
  "ami": {
    "options": {
      "stop_instance_before_creation": true,
      "wait_for_completion": false,
      "terminate_instance_after_creation": false
    },
    "tags": {
      "AMIProject": "MyProject",
      "AMIEnvironment": "Production"
    }
  }
}
```

**Supported Runtime Override Parameters:**

- **`ec2.key_name`** - EC2 key pair name for SSH access to the Mac instance
- **`ec2.tags`** - Additional tags to apply to the launched EC2 instance (merged with config tags)
- **`ami.options.stop_instance_before_creation`** - Whether to stop the instance before creating the AMI
- **`ami.options.wait_for_completion`** - Whether to wait for AMI creation to complete before proceeding (now handled by separate Step Function steps for better reliability)
- **`ami.options.terminate_instance_after_creation`** - Whether to terminate the instance after AMI creation
- **`ami.tags`** - Additional tags to apply to the created AMI (merged with config tags)

Parameters passed at execution time override the corresponding config.json values.

## Execution

### Via AWS Console

1. Go to Step Functions in AWS Console
2. Find "DCVMacImageAutomationStateMachine"
3. Click "Start execution"
4. Provide input JSON (optional)
5. Monitor execution progress

### Via AWS CLI

```bash
# Start execution with structured parameters
aws stepfunctions start-execution \
  --state-machine-arn arn:aws:states:region:account:stateMachine:DCVMacImageAutomationStateMachine \
  --input '{
    "ec2": {
      "key_name": "your-ec2-key-pair"
    },
    "ami": {
      "options": {
        "stop_instance_before_creation": true,
        "wait_for_completion": false
      }
    }
  }'
```

## Monitoring and Debugging

### CloudWatch Logs

Each Lambda function writes to CloudWatch Logs:
- `/aws/lambda/DCVMacAutomationStack-LaunchEC2Lambda-xxx`
- `/aws/lambda/DCVMacAutomationStack-MacSIPPollerLambda-xxx`
- `/aws/lambda/DCVMacAutomationStack-CheckEC2StatusLambda-xxx`
- `/aws/lambda/DCVMacAutomationStack-RunSSMCommandLambda-xxx`
- `/aws/lambda/DCVMacAutomationStack-CreateImageLambda-xxx`
- `/aws/lambda/DCVMacAutomationStack-StopInstanceLambda-xxx`
- `/aws/lambda/DCVMacAutomationStack-CheckInstanceStoppedLambda-xxx`
- `/aws/lambda/DCVMacAutomationStack-PollAMIStatusLambda-xxx`
- `/aws/lambda/DCVMacAutomationStack-TerminateInstanceLambda-xxx`

### Step Function Execution History

View detailed execution history in the Step Functions console to see:
- Input/output for each step
- Execution timeline
- Error details if any step fails

## Customization Guide

### ⚡ Quick Customization (config.json)

All major customizations can be done through `config.json`:

**Change Mac Instance Settings:**
```json
{
  "ec2": {
    "ami_id": "ami-your-mac-ami",
    "instance_type": "mac2.metal",
    "placement": {
      "tenancy": "host",
      "host_id": "h-your-dedicated-host-id"
    }
  }
}
```

**Customize User Data**: Edit the Mac user data script directly in `lambda/launch_ec2.py` to modify DCV server installation and configuration

**Configure Mac SIP Monitoring:**
```json
{
  "mac_monitoring": {
    "polling_interval_minutes": 5,
    "timeout_hours": 5
  }
}
```

**Set AMI Options:**
```json
{
  "ami": {
    "options": {
      "stop_instance_before_creation": true,
      "wait_for_completion": true,
      "terminate_instance_after_creation": true
    }
  }
}
```

### 🔧 Advanced Customization (Code Changes)

For complex customizations beyond config.json options:

- **Custom EC2 Setup & DCV Configuration**: Modify `lambda/launch_ec2.py`
- **Mac SIP Polling Logic**: Enhance `lambda/api_poller.py`
- **EC2 Status Monitoring**: Customize `lambda/check_ec2_status.py`
- **SSM Command Execution**: Extend `lambda/run_ssm_command.py` for DCV installation
- **AMI Processing**: Extend `lambda/create_image.py`
- **Instance Stop Logic**: Customize `lambda/stop_instance.py` and `lambda/check_instance_stopped.py`
- **AMI Polling Logic**: Enhance `lambda/poll_ami_status.py`
- **Instance Termination**: Modify `lambda/terminate_instance.py`
- **Infrastructure**: Update `automation/automation_stack.py`

## Error Handling

The workflow includes error handling for:
- EC2 launch failures
- Mac SIP modification task failures
- EC2 instance status check failures
- SSM command execution failures
- DCV server installation issues
- AMI creation problems
- Invalid instance states

Failed executions will provide detailed error information in the Step Function execution history.

## Cost Considerations

- **EC2 Instances**: Charged for running time
- **Lambda**: Pay per invocation and duration
- **Step Functions**: Pay per state transition
- **AMI Storage**: EBS snapshot costs

## Cleanup

To avoid ongoing charges:

```bash
# Delete the stack
cdk destroy

# Note: AMIs created by the automation need to be manually deleted as they are retained for safety
```

## Security Notes

1. **IAM Permissions**: The Lambda execution role uses least-privilege permissions with only the specific EC2, SSM, and IAM actions required for the automation.
2. **Mac Instance Access**: Mac instances require specific IAM permissions for SIP modification tasks.
3. **VPC Security**: The security group allows SSH access. Restrict as needed for Mac instances.
4. **Instance Profile**: Mac instances have SSM access for DCV server installation and management. Adjust permissions as required.
5. **DCV License Access**: EC2 instances need access to S3 buckets containing DCV licenses (DCV server is now downloaded via HTTPS).

### Required IAM Permissions

#### Lambda Execution Role Permissions
The Lambda functions require these permissions (currently using managed policies for simplicity):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ec2:DescribeMacModificationTasks",
        "ec2:CreateImage",
        "ec2:CreateTags",
        "ec2:DescribeImages",
        "ec2:DescribeInstances",
        "ec2:DescribeInstanceStatus",
        "ec2:RunInstances",
        "ec2:StopInstances",
        "ec2:TerminateInstances",
        "ssm:SendCommand",
        "ssm:GetCommandInvocation",
        "ssm:DescribeInstanceInformation",
        "ssm:ListCommandInvocations",
        "iam:PassRole"
      ],
      "Resource": "*"
    }
  ]
}
```

#### EC2 Instance Profile Permissions
The Mac EC2 instances require these permissions:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ec2:CreateMacSystemIntegrityProtectionModificationTask"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject"
      ],
      "Resource": [
        "arn:aws:s3:::dcv-license.*/*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject"
      ],
      "Resource": [
        "arn:aws:s3:::your-dcv-build-bucket/*"
      ],
      "Condition": {
        "Note": "This permission is automatically added only when dcv_server_build_location uses an S3 URI"
      }
    }
  ]
}
```

**Note**: The CDK stack implements these exact least-privilege permissions. No overly broad managed policies like `AmazonEC2FullAccess` are used.

## Troubleshooting

### Configuration Issues

```bash
# Validate configuration first
python3 validate_config.py

# Check configuration warnings
python3 validate_config.py template
```

### Common Issues

1. **Configuration Errors**: Run `python3 validate_config.py` to check config.json
2. **Permission Errors**: Check IAM roles have necessary permissions for EC2, SSM, and S3
3. **Network Issues**: Verify VPC configuration and security groups in config.json
4. **Mac SIP API Failures**: Check EC2 permissions for `describe_mac_modification_tasks`
5. **SSM Command Failures**: Verify SSM agent is running and instance has proper IAM role
6. **DCV Installation Issues**: Check S3 access to DCV packages and installation logs
7. **AMI Creation Fails**: Ensure Mac instance is in valid state and has sufficient permissions

### Debug Steps

1. **Configuration**: Use `validate_config.py` to verify settings
2. **CloudWatch Logs**: Check logs for each Lambda function
3. **Step Function**: Review execution details in AWS Console
4. **Mac Instance Status**: Verify Mac instance status in AWS Console
5. **SSM Status**: Check SSM agent status and command execution history
6. **DCV Installation**: Verify DCV server installation logs on the Mac instance
7. **SIP Task Testing**: Test `describe_mac_modification_tasks` API manually with AWS CLI
