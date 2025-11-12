#!/usr/bin/env python3
import os
import aws_cdk as cdk
from automation.automation_stack import AutomationStack

# Validate required environment variables
account = os.getenv('CDK_DEFAULT_ACCOUNT')
region = os.getenv('CDK_DEFAULT_REGION')

if not account:
    raise EnvironmentError("CDK_DEFAULT_ACCOUNT environment variable is required")
if not region:
    raise EnvironmentError("CDK_DEFAULT_REGION environment variable is required")

app = cdk.App()
AutomationStack(app, "DCVMacImageAutomationStack",
    description='(uksb-1tupboc66) (tag:dcv-mac-image-automation)',
    env=cdk.Environment(
        account=account,
        region=region
    ),
)

app.synth()