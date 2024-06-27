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
from aws_cdk import Stack
import aws_cdk as cdk
import aws_cdk.aws_ec2 as ec2
import aws_cdk.aws_iam as iam
import aws_cdk.aws_kms as kms
import aws_cdk.aws_ssm as ssm
from constructs import Construct

# The DCV Access Console stack
class DcvAccessConsole(Stack):
    """ Class to deploy DCV infrastructure components """
    def __init__(self, scope: Construct, construct_id: str, config_data: dict, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Create reference for VPC
        vpc = ec2.Vpc.from_lookup(self, "VPC", vpc_id=config_data['network']['vpcId'])
        # Create references for target subnet
        # using subnet_ids pulled from config.json
        subnet_ref = ec2.Subnet.from_subnet_attributes(
            self, "SubnetFromAttributes",
            subnet_id=config_data['network']['accessConsoleSubnetId'],
            availability_zone=config_data['network']['subnetAZ']
            )
        subnet_target = ec2.SubnetSelection(
            subnets=[subnet_ref]
            )

        # IAM Fleet Role Configuration
        role_access_console = iam.Role(self, "AccessConsoleRole",
                        assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
                        role_name="dcv-access-console-role"
                        )

        role_access_console.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name("AmazonSSMManagedInstanceCore")
        )

        role_access_console.add_to_policy(iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=[
                'ssm:DescribeParameters'
                ],
            resources=[
                f"arn:aws:ssm:{self.region}:{self.account}:parameter/*",
                ]
        ))

        role_access_console.add_to_policy(iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=[
                'ssm:GetParameter'
                ],
            resources=[
                f"arn:aws:ssm:{self.region}:{self.account}:parameter/dcv-*",
                ]
        ))

        # Access Console Security Group configuration
        sg_access_console = ec2.SecurityGroup(self, "AccessConsoleSecurityGroup",
                               vpc=vpc,
                               description="Security Group for the DCV Access Console",
                               allow_all_outbound=True, #Egress all
                               disable_inline_rules=True
                               )

        # Add Ingress for Access Console
        sg_access_console.add_ingress_rule(
            ec2.Peer.ipv4(f"{config_data['accessConsole']['inboundAccess']}"), ec2.Port.tcp(443), \
                "Allow HTTPS traffic to the DCV Access Console"
            )

        # Get KMS Key from Alias/Key Name
        kms_arn = f"arn:aws:kms:{self.region}:{self.account}:alias/{config_data['kmsKeyName']}"
        kms_key = kms.Key.from_key_arn(self, "kms-key", kms_arn)

        # SSM parameters to hold config values
        ssm.StringParameter(self, "brokerCredentials",
            description="Client credentials for DCV Session Manager",
            parameter_name="dcv-session-manager-credentials",
            string_value=f"{config_data['accessConsole']['smClientId']}:{config_data['accessConsole']['smClientPsw']}",
            tier=ssm.ParameterTier.STANDARD
        )

        ssm.StringParameter(self, "brokerDns",
            description="Reachable DNS of DCV Session Manager",
            parameter_name="dcv-session-manager-dns",
            string_value=f"{config_data['accessConsole']['sessionMgrDns']}",
            tier=ssm.ParameterTier.STANDARD
        )

        if config_data['accessConsole']['gatewayDns'] != "":
            ssm.StringParameter(self, "gwyDns",
                description="Reachable DNS of DCV Connection Gateway",
                parameter_name="dcv-connection-gwy-dns",
                string_value=f"{config_data['accessConsole']['gatewayDns']}",
                tier=ssm.ParameterTier.STANDARD
            )

        if config_data['accessConsole']['adminUser'] != "ec2-user":
            ssm.StringParameter(self, "accessConsoleAdmin",
                description="Admin user to set for Access Console",
                parameter_name="dcv-access-console-admin",
                string_value=f"{config_data['accessConsole']['gatewayDns']}",
                tier=ssm.ParameterTier.STANDARD
            )


        # DCV Access Console
        ### DCV Access Console AMI
        session_mgr_ami = ec2.GenericLinuxImage({
            self.region : config_data['accessConsole']['amiId']
            }
        )

        # Add the user data script to custom string
        access_console_user_data_file = open(os.path.join(os.path.dirname( __file__ ),
                                                       "..", "..",
                                                       "scripts",
                                                       "access-console-user-data.sh"),
                                                       "r", encoding="utf-8")
        access_console_user_data_content = access_console_user_data_file.read()
        access_console_user_data = ec2.UserData.custom(access_console_user_data_content)

        # Create a reference to the SSH Key Pair name given in the config.json file
        key_pair = ec2.KeyPair.from_key_pair_attributes(self, "DCVKeyPair",
            key_pair_name=config_data['sshKeypairName']
        )

        # Create the Session Manager EC2 instance
        access_console_instance = ec2.Instance(self, "AccessConsoleInstance",
                                vpc=vpc,
                                vpc_subnets=subnet_target,
                                instance_type=ec2.InstanceType.of(
                                    ec2.InstanceClass.M6G, ec2.InstanceSize.LARGE),
                                machine_image=session_mgr_ami,
                                security_group=sg_access_console,
                                key_pair=key_pair,
                                user_data=access_console_user_data,
                                role=role_access_console,
                                block_devices=[ec2.BlockDevice(
                                    device_name="/dev/xvda",
                                    volume=ec2.BlockDeviceVolume.ebs(
                                        8, encrypted=True, kms_key=kms_key))]
                                )

        cdk.CfnOutput(self, "AccessConsoleURL", \
                    value= f"You can access the console at https://{access_console_instance.instance_public_dns_name} or privately at https://{access_console_instance.instance_private_dns_name}")
