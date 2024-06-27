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

import json
import aws_cdk as cdk
from stacks.dcv_ac_infra.dcv_ac_infra import DcvAccessConsole

app = cdk.App()

# Load the app configuration from the config.json file
try:
    with open("config.json", "r") as config_file:
        config_data = json.load(config_file)
except Exception as e:
    print(f"Could not read the app configuration file. {e}")
    raise e


# Set CDK environment variables
environment = cdk.Environment(account=config_data['accountId'], region=config_data['region'])

# Create the DCV Infrastructure Stack for Session Manager and Connection Gateway
DcvAccessConsole(app, "DcvAccessConsole",
         description='(uksb-1tupboc66) (tag:dcv-access-console)',
         config_data=config_data,
         env=environment)

app.synth()