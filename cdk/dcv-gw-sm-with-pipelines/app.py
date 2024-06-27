# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
#
# Permission is hereby granted, free of charge, to any person obtaining a copy of
# this software and associated documentation files (the "Software"), to deal in
# the Software without restriction, including without limitation the rights to
# use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of
# the Software, and to permit persons to whom the Software is furnished to do so.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS
# FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
# COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER
# IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
# CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

import os
import json
import aws_cdk as cdk
from stacks.dcv_ami.dcv_ami import DcvAmi
from stacks.dcv_infra.dcv_infra import DcvInfra

app = cdk.App()

# Load the app configuration from the config.json file
try:
    with open("config.json", "r", encoding="utf-8") as config_file:
        config_data = dict(json.load(config_file))
except Exception as e:
    print(f"Could not read the app configuration file. {e}")
    raise e

# Get the contents of the Session Manager component file
session_mgr_component = open(os.path.join(os.path.dirname( __file__ ),
                                 "components",
                                 "build-dcv-session-mgr.yaml"),
                                 "r", encoding="utf-8").read()

# Get the contents of the Connection Gateway component file
connection_gwy_component = open(os.path.join(os.path.dirname( __file__ ),
                                 "components",
                                 "build-dcv-connection-gwy.yaml"),
                                 "r", encoding="utf-8").read()

# Set CDK environment variables
environment = cdk.Environment(account=config_data['accountId'], region=config_data['region'])

# Create the DCV AMI Builder Stack for Session Manager
session_mgr_ami = DcvAmi(app, "SessionMgrAmiStack",
                         description='(uksb-1tupboc66) (tag:dcv-session-mgr-pipeline)',
                         image_pipeline_name="dcv-session-mgr-ami",
                         component_content=session_mgr_component,
                         instance_type="m6g.large",
                         config_data=config_data,
                         env=environment)

# Create the DCV AMI Builder Stack for Connection Gateway
connection_gwy_ami= DcvAmi(app, "ConnectionGwyAmiStack",
                           description='(uksb-1tupboc66) (tag:dcv-connection-gwy-pipeline)',
                           image_pipeline_name="dcv-connection-gwy-ami",
                           component_content=connection_gwy_component,
                           instance_type="c7g.large",
                           config_data=config_data,
                           env=environment)

# Create the DCV Infrastructure Stack for Session Manager and Connection Gateway
DcvInfra(app, "DcvInfraStack",
         description='(uksb-1tupboc66) (tag:dcv-gw-sm-with-pipelines)',
         config_data=config_data,
         env=environment)

app.synth()
