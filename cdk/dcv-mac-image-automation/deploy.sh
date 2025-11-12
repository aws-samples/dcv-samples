#!/bin/bash

# AWS EC2 Automation Deployment Script
# This script helps deploy the CDK stack and Lambda functions for Mac SIP automation

set -e  # Exit on any error

echo "Starting AWS EC2 Mac SIP Automation Deployment"
echo "=================================================="
echo "This deployment includes:"
echo "  • EC2 Mac instance automation"
echo "  • Mac SIP (System Integrity Protection) management"
echo "  • Amazon DCV server automation"
echo "  • Automated AMI creation workflow"
echo ""

# Check if virtual environment exists
if [ ! -d ".venv" ]; then
    echo "Creating Python virtual environment..."
    python3 -m venv .venv
fi

# Activate virtual environment
echo "Activating virtual environment..."
source .venv/bin/activate

# Install CDK dependencies
echo "Installing CDK dependencies..."
pip install -r requirements.txt

# Install Lambda dependencies
echo "🔧 Installing Lambda dependencies..."
cd lambda
pip install -r requirements.txt -t .
cd ..

# Check Python version
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}' | cut -d. -f1,2)
REQUIRED_VERSION="3.11"
echo "🐍 Python version: $PYTHON_VERSION (required: $REQUIRED_VERSION+)"
if [ "$(printf '%s\n' "$REQUIRED_VERSION" "$PYTHON_VERSION" | sort -V | head -n1)" != "$REQUIRED_VERSION" ]; then
    echo "Warning: Python $REQUIRED_VERSION+ is recommended for optimal compatibility"
fi

# Check if CDK is installed
if ! command -v cdk &> /dev/null; then
    echo "AWS CDK is not installed. Please install it first:"
    echo "   npm install -g aws-cdk"
    exit 1
fi

# Check AWS credentials
echo "🔐 Checking AWS credentials..."
if ! aws sts get-caller-identity &> /dev/null; then
    echo "AWS credentials not configured. Please run:"
    echo "   aws configure"
    exit 1
fi

ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
REGION=$(aws configure get region)

echo "AWS Account: $ACCOUNT"
echo "AWS Region: $REGION"

# Validate region is configured
if [ -z "$REGION" ]; then
    echo "AWS region not configured. Please run:"
    echo "   aws configure set region <your-region>"
    exit 1
fi

# Bootstrap CDK if needed
echo "Checking CDK bootstrap..."
if ! aws cloudformation describe-stacks --stack-name CDKToolkit --region $REGION &> /dev/null; then
    echo "Bootstrapping CDK..."
    cdk bootstrap
else
    echo "CDK already bootstrapped"
fi

# Validate configuration
echo "Validating configuration..."
if ! python3 validate_config.py; then
    echo "Configuration validation failed!"
    echo "Please fix the issues in config.json and try again."
    echo ""
    echo "Helpful commands:"
    echo "   python3 validate_config.py template  - Show configuration field explanations"
    echo "   python3 validate_config.py --help    - Show validation help"
    exit 1
fi

# Check for Mac-specific requirements
echo "Checking Mac2-specific requirements..."
MAC_INSTANCE_TYPE=$(python3 -c "from automation.config_loader import ConfigLoader; c=ConfigLoader(); print(c.get('ec2.instance_type', ''))" 2>/dev/null || echo "")
echo "Mac2 instance type detected: $MAC_INSTANCE_TYPE"

# Check for required Mac configurations
HOST_ID=$(python3 -c "from automation.config_loader import ConfigLoader; c=ConfigLoader(); print(c.get('ec2.placement.host_id', '') or 'NOT_SET')" 2>/dev/null || echo "NOT_SET")
if [ "$HOST_ID" = "NOT_SET" ]; then
    echo "Warning: No dedicated host ID specified for Mac2 instance"
    echo "   Mac2 instances require a dedicated host. Consider setting ec2.placement.host_id"
else
    echo "Dedicated host ID configured: $HOST_ID"
fi

# Check for DCV configuration
DCV_PASSWORD=$(python3 -c "from automation.config_loader import ConfigLoader; c=ConfigLoader(); print('SET' if c.get('ec2.ec2_user_password') else 'NOT_SET')" 2>/dev/null || echo "NOT_SET")
if [ "$DCV_PASSWORD" = "NOT_SET" ]; then
    echo "Warning: No EC2 user password configured for DCV automation"
    echo "   Consider setting ec2.ec2_user_password for DCV session automation"
else
    echo "DCV user password configured"
fi

# Synthesize CloudFormation template
echo "Synthesizing CDK template..."
cdk synth

# Deploy the stack
echo "Deploying stack..."
echo "This may take 5-10 minutes..."

# Get stack name for later reference
STACK_NAME=$(python3 -c "from automation.config_loader import ConfigLoader; c=ConfigLoader(); print(c.get('step_function.name', 'MacSIPAutomationStateMachine').replace('StateMachine', 'Stack'))" 2>/dev/null || echo "AutomationStack")

cdk deploy --require-approval never

echo ""
echo "Deployment completed successfully!"
echo ""

# Get deployed resources info
STEP_FUNCTION_NAME=$(python3 -c "from automation.config_loader import ConfigLoader; c=ConfigLoader(); print(c.get('step_function.name', 'MacSIPAutomationStateMachine'))" 2>/dev/null || echo "MacSIPAutomationStateMachine")
REGION=$(aws configure get region)

echo "Deployed Resources:"
echo "  Stack Name: $STACK_NAME"
echo "  Step Function: $STEP_FUNCTION_NAME"
echo "  Region: $REGION"
echo ""

echo "Next Steps:"
echo "1. View your Step Function:"
echo "   AWS Console: https://$REGION.console.aws.amazon.com/states/home?region=$REGION#/statemachines"
echo ""
echo "2. Test the automation:"
echo "   In the AWS console, go to the Step Functions console and start a new execution."
echo "   Example execution input: '{\"key_name\": \"KeyPairName\", \"stop_instance\": true, \"wait_for_ami\": false}'"
echo "   You can also use the AWS CLI to start an execution:"
echo "   aws stepfunctions start-execution --state-machine-arn arn:aws:states:$REGION:123456789012:stateMachine:MacSIPAutomationStateMachine --input '{\"key_name\": \"KeyPairName\", \"stop_instance\": true, \"wait_for_ami\": false}'"
echo ""
echo "3. Monitor execution:"
echo "   - Step Functions console for workflow status"
echo "   - CloudWatch Logs for detailed Lambda function logs"
echo "   - EC2 console for instance and AMI creation"
echo ""
echo "4. Additional resources:"
echo "   - README.md - Complete documentation"
echo "   - CONFIGURATION_GUIDE.md - Configuration reference"
echo "   - MAC_SIP_WORKFLOW.md - Mac SIP automation details"
echo ""

echo "Mac2 (Apple Silicon) Specific Notes:"
echo "   - Ensure you have available Mac2 dedicated hosts in $REGION"
echo "   - Mac2 instances take 10-15 minutes to launch and configure"
echo "   - SIP modification requires macOS 13, 14, or 15 (Apple Silicon)"
echo "   - AMI creation for Mac2 instances can take 45-60 minutes"
echo "   - DCV server automation requires Apple Silicon architecture"
echo ""

echo "Cleanup:"
echo "   To remove all resources: cdk destroy"
echo "   To remove just the stack: aws cloudformation delete-stack --stack-name $STACK_NAME"
echo ""

echo "Troubleshooting:"
echo "   - Configuration issues: python3 validate_config.py"
echo "   - View logs: aws logs tail /aws/lambda/[function-name] --follow"
echo "   - Stack status: aws cloudformation describe-stacks --stack-name $STACK_NAME"