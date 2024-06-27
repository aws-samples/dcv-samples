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
import aws_cdk.aws_autoscaling as autoscaling
import aws_cdk.aws_elasticloadbalancingv2 as elbv2
from constructs import Construct

# The NICE DCV INFRA stack
class DcvInfra(Stack):
    """ Class to deploy DCV infrastructure components """
    def __init__(self, scope: Construct, construct_id: str, config_data: dict, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

         # Check if a VPC and subnets were provided in the config.json file
        if config_data['network']['vpcId'] and config_data['network']['publicASubnetId'] \
            and config_data['network']['publicBSubnetId'] \
                and config_data['network']['privateASubnetId'] \
                    and config_data['network']['privateBSubnetId']:
            # Create reference for VPC
            vpc = ec2.Vpc.from_lookup(self, "VPC", vpc_id=config_data['network']['vpcId'])
            # Create references for private and public subnets
            # using subnet_ids pulled from config.json
            subnets_public_ref_a = ec2.Subnet.from_subnet_attributes(
                self, "PublicSubnetAFromAttributes",
                subnet_id=config_data['network']['publicASubnetId'],
                availability_zone=f"{self.region}a"
                )
            subnets_public_ref_b = ec2.Subnet.from_subnet_attributes(
                self, "PublicSubnetBFromAttributes",
                subnet_id=config_data['network']['publicBSubnetId'],
                availability_zone=f"{self.region}b"
                )
            subnets_private_ref_a = ec2.Subnet.from_subnet_attributes(
                self, "PrivateSubnetAFromAttributes",
                subnet_id=config_data['network']['privateASubnetId'],
                availability_zone=f"{self.region}a"
                )
            subnets_private_ref_b = ec2.Subnet.from_subnet_attributes(
                self, "PrivateSubnetBFromAttributes",
                subnet_id=config_data['network']['privateBSubnetId'],
                availability_zone=f"{self.region}b"
                )
            subnets_public = ec2.SubnetSelection(
                subnets=[subnets_public_ref_a, subnets_public_ref_b]
                )
            subnets_private = ec2.SubnetSelection(
                subnets=[subnets_private_ref_a, subnets_private_ref_b]
                )
        else:
            # Create new VPC, subnets, and NAT Gateway
            vpc = ec2.Vpc(self, "VPC",
                        nat_gateways = 1,
                        max_azs = 2,
                        subnet_configuration=[
                            ec2.SubnetConfiguration(
                                name = "public-subnet",
                                subnet_type = ec2.SubnetType.PUBLIC,
                                cidr_mask = 24,
                                ),
                            ec2.SubnetConfiguration(
                                name = "private-subnet",
                                subnet_type = ec2.SubnetType.PRIVATE_WITH_EGRESS,
                                cidr_mask = 24
                                )
                        ],
            )
            # Create references for private and public subnets
            # using availability zones described above
            subnets_public = ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PUBLIC
                )
            subnets_private = ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS
                )


        # IAM Fleet Role Configuration
        role_fleet = iam.Role(self, "DCVFleetRole",
                        assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
                        role_name="dcv-fleet-role"
                        )

        # IAM Session Manager Role Configuration
        role_session_mgr = iam.Role(self, "DCVSessionMgrRole",
                        assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
                        role_name="dcv-session-mgr-role"
                        )

        # IAM Connection Gateway Role Configuration
        role_connection_gwy = iam.Role(self, "DCVConnectionGwyRole",
                        assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
                        role_name="dcv-connection-gwy-role"
                        )

        # Permission to get NICE DCV License for fleet role
        role_fleet.add_to_policy(iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=["s3:GetObject"],
            resources=[f"arn:aws:s3:::dcv-license.{self.region}/*"]
        ))

        role_fleet.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name("AmazonSSMManagedInstanceCore")
        )

        iam.CfnInstanceProfile(self, "DCVServerInstanceProfile",
            instance_profile_name="dcv-server-profile",
            roles=[role_fleet.role_name]
        )

        # Permission for SSM Parameter for Session Manager instance
        role_session_mgr.add_to_policy(iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=[
                'ssm:DescribeParameters'
                ],
            resources=[
                f"arn:aws:ssm:{self.region}:{self.account}:parameter/*",
                ]
        ))

        role_session_mgr.add_to_policy(iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=[
                'ssm:PutParameter',
                'ssm:GetParameter'
                ],
            resources=[
                f"arn:aws:ssm:{self.region}:{self.account}:parameter/dcv-broker-private-dns",
                ]
        ))

        role_session_mgr.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name("AmazonSSMManagedInstanceCore")
        )

        # Permission for SSM Parameter for Session Manager instance
        role_connection_gwy.add_to_policy(iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=[
                'ssm:DescribeParameters'
                ],
            resources=[
                f"arn:aws:ssm:{self.region}:{self.account}:parameter/*",
                ]
        ))

        # Permission to read the SSM Parameter for Connection Gateway instance
        role_connection_gwy.add_to_policy(iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=[
                'ssm:GetParameter'
                ],
            resources=[
                f"arn:aws:ssm:{self.region}:{self.account}:parameter/dcv-broker-private-dns"
                ]
        ))

        # Add managed policy to allow CloudWatch logs and SSM
        role_connection_gwy.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name("AmazonSSMManagedInstanceCore"))

        # Session Manager Security Group configuration
        sg_session_mgr = ec2.SecurityGroup(self, "SMSecurityGroup",
                               vpc=vpc,
                               description="Default ports for DCV Session, Gateway, and Broker",
                               allow_all_outbound=True, #Egress all
                               disable_inline_rules=True
                               )

        # Add Ingress for Nice DCV TCP/UDP Ports
        sg_session_mgr.add_ingress_rule(
            ec2.Peer.any_ipv4(), ec2.Port.tcp(8443), "allow CLI to Broker communication"
            )
        sg_session_mgr.add_ingress_rule(
            ec2.Peer.any_ipv4(), ec2.Port.tcp(8445), "allow Agent to Broker communication"
            )
        sg_session_mgr.add_ingress_rule(
            sg_session_mgr, ec2.Port.all_traffic(), "allow Broker to Broker communication"
            )

        # Connection Gateway Security Group configuration
        sg_connection_gwy = ec2.SecurityGroup(self, "CGSecurityGroup",
                               vpc=vpc,
                               description="SG default ports for DCV Connection Gateway",
                               allow_all_outbound=True, #Egress all
                               disable_inline_rules=True
                               )

        sg_connection_gwy.add_ingress_rule(
            ec2.Peer.any_ipv4(), ec2.Port.tcp(8443), "allow TCP DCV access from public internet"
            )
        sg_connection_gwy.add_ingress_rule(
            ec2.Peer.any_ipv4(), ec2.Port.udp(8443), "allow UDP DCV access from public internet"
            )
        sg_connection_gwy.add_ingress_rule(
            ec2.Peer.any_ipv4(), ec2.Port.tcp(8989), "allow health check for NLB targets"
            )

        # Gateway to Session Manager resolver communication
        sg_session_mgr.add_ingress_rule(
            sg_connection_gwy, ec2.Port.tcp(8447), "allow Gateway to Broker resolver communication"
            )

        # DCV server fleet Security Group configuration
        sg_dcv_server = ec2.SecurityGroup(self, "DCVServerSecurityGroup",
                               vpc=vpc,
                               description="SG default ports for DCV Connection Gateway",
                               allow_all_outbound=True, #Egress all
                               disable_inline_rules=True
                               )

        sg_dcv_server.add_ingress_rule(
            sg_connection_gwy, ec2.Port.tcp(8443), "allow DCV streaming traffic from Gateway"
            )
        sg_dcv_server.add_ingress_rule(
            sg_connection_gwy, ec2.Port.udp(8443), "allow DCV streaming traffic from Gateway"
            )

        # Get KMS Key from Alias/Key Name
        kms_arn = f"arn:aws:kms:{self.region}:{self.account}:alias/{config_data['kmsKeyName']}"
        kms_key = kms.Key.from_key_arn(self, "kms-key", kms_arn)

        # Session Manager
        ### Session Manager AMI
        session_mgr_ami = ec2.GenericLinuxImage({
            self.region : config_data['sessionMgr']['baseAmiId']
            }
        )

        # Add the user data script to custom string
        session_mgr_user_data_file = open(os.path.join(os.path.dirname( __file__ ),
                                                       "..", "..",
                                                       "scripts",
                                                       "session-mgr-user-data.sh"),
                                                       "r", encoding="utf-8")
        session_mgr_user_data_content = session_mgr_user_data_file.read()
        session_mgr_user_data = ec2.UserData.custom(session_mgr_user_data_content)

        # Create a reference to the SSH Key Pair name given in the config.json file
        key_pair = ec2.KeyPair.from_key_pair_attributes(self, "DCVKeyPair",
            key_pair_name=config_data['sshKeypairName']
        )

        # Create the Session Manager EC2 instance
        session_mgr_instance = ec2.Instance(self, "SessionMgrInstance",
                                vpc=vpc,
                                vpc_subnets=subnets_private,
                                instance_type=ec2.InstanceType.of(
                                    ec2.InstanceClass.M6G, ec2.InstanceSize.LARGE),
                                machine_image=session_mgr_ami,
                                security_group=sg_session_mgr,
                                key_pair=key_pair,
                                user_data=session_mgr_user_data,
                                role=role_session_mgr,
                                block_devices=[ec2.BlockDevice(
                                    device_name="/dev/xvda",
                                    volume=ec2.BlockDeviceVolume.ebs(
                                        8, encrypted=True, kms_key=kms_key))]
                                )

        # Connection Gateway
        ### Connection Gateway AMI
        connection_gwy_ami = ec2.GenericLinuxImage({
            self.region : config_data['connectionGwy']['baseAmiId']
        })

       # Add the user data script to custom string
        connection_gwy_user_data_file = open(os.path.join(os.path.dirname( __file__ ),
                                                          "..", "..",
                                                          "scripts",
                                                          "connection-gwy-user-data.sh"),
                                                          "r", encoding="utf-8")

        connection_gwy_user_data_content = connection_gwy_user_data_file.read()
        connection_gwy_session_mgr_user_data = ec2.UserData.custom(connection_gwy_user_data_content)

        # Create an EC2 launch template with the encrypted volume for Connection Gateway
        connection_gwy_launch_template = ec2.LaunchTemplate(self, "ConnectionGwyLaunchTemplate",
                                             machine_image=connection_gwy_ami,
                                             security_group=sg_connection_gwy,
                                             instance_type=ec2.InstanceType.of(
                                                 ec2.InstanceClass.C7G, ec2.InstanceSize.LARGE),
                                             key_pair=key_pair,
                                             user_data=connection_gwy_session_mgr_user_data,
                                             role=role_connection_gwy,
                                             block_devices=[ec2.BlockDevice(
                                                 device_name="/dev/xvda",
                                                 volume=ec2.BlockDeviceVolume.ebs(
                                                     8, encrypted=True, kms_key=kms_key))],
                                            )

        # Create a Connection Gateway Auto Scaling Group
        connection_gwy_asg = autoscaling.AutoScalingGroup(self, "ConnectionGwyASG",
                                     vpc=vpc,
                                     launch_template=connection_gwy_launch_template,
                                     min_capacity=1,
                                     max_capacity=5,
                                     desired_capacity=1,
                                     vpc_subnets=subnets_private
                                    )

        # Ensure Session Manager instance is created before Connection Gateway targets
        connection_gwy_asg.node.add_dependency(session_mgr_instance)

        # Connection Gateway Auto Scaling Group CPU Utilization to scale
        connection_gwy_asg.scale_on_cpu_utilization(
            "ConnectionGwyASGCPUUtilization", target_utilization_percent=75
            )

        # Create a Connection Gateway Network Load Balancer
        connection_gwy_nlb = elbv2.NetworkLoadBalancer(self, "ConnectionGwyNLB",
                                        vpc=vpc,
                                        internet_facing=True,
                                        vpc_subnets=subnets_public,
                                        load_balancer_name="connection-gwy-nlb",
                                        cross_zone_enabled=True
                                        )

        # Connection Gateway Listener to Target Setup for NLB
        connection_gwy_listener = connection_gwy_nlb.add_listener(
            "ConnectionGwyNLBListener", port=8443, protocol=elbv2.Protocol.TCP_UDP
            )

        # Route the Connection Gateway targets
        connection_gwy_listener.add_targets("ConnectionGwyNLBTarget",
                                            port=8443,
                                            protocol=elbv2.Protocol.TCP_UDP,
                                            health_check=elbv2.HealthCheck(
                                                port="8989",
                                                protocol=elbv2.Protocol.TCP,
                                                unhealthy_threshold_count=5,
                                                healthy_threshold_count=5,
                                                interval=cdk.Duration.seconds(30)
                                                ),
                                            targets=[connection_gwy_asg]
                                            )
