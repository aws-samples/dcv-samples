"""
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
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
"""

from aws_cdk import (
    Stack,
    aws_imagebuilder as imagebuilder,
    aws_iam as iam,
    aws_ec2 as ec2
)
from constructs import Construct

# The NICE DCV AMI stack
class DcvAmi(Stack):
    def __init__(self, scope: Construct, construct_id: str, image_pipeline_name: str,
                 component_content: str, instance_type: str, config_data: dict, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Component to install for Session Manager or Connection Gateway
        component = imagebuilder.CfnComponent(self,
                        image_pipeline_name,
                        name=f"{image_pipeline_name}-component",
                        platform="Linux",
                        version="1.0.0",
                        data=component_content
                    )

        # Recipe that installs all of above components together with a base image
        recipe = imagebuilder.CfnImageRecipe(self,
                    f"{image_pipeline_name}-recipe",
                    name=f"{image_pipeline_name}-recipe",
                    version="1.0.0",
                    components=[
                        {"componentArn": component.attr_arn},
                        {"componentArn": "arn:aws:imagebuilder:us-east-1:aws:component/aws-cli-version-2-linux/1.0.4/1"}
                    ],
                    parent_image=config_data['sessionMgr']['baseAmiId']
                )

        # Distribution to specified accounts and regions
        imagebuilder.CfnDistributionConfiguration(self,
            f"{image_pipeline_name}-dist-config",
            name=f"{image_pipeline_name}-dist-config",
            distributions=[{"region": self.region,
                            "amiDistributionConfiguration": {
                                "name": image_pipeline_name + "-{{ imagebuilder:buildDate }}",
                                "description": "NICE DCV AMI",
                                "targetAccountIds": [ self.account ]
                            }
                        }]
        )

        # Role for pipeline and instance (ImageBuilder, Logs, and SSM)
        role = iam.Role(self, f"{image_pipeline_name}-role",
            role_name=f"{image_pipeline_name}-role",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com")
        )
        role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name("AmazonSSMManagedInstanceCore")
        )
        role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name("EC2InstanceProfileForImageBuilder")
        )

        # Create an instance profile for infrastructure config            
        instance_profile = iam.CfnInstanceProfile(self,
                                f"{image_pipeline_name}-instance-profile",
                                instance_profile_name=f"{image_pipeline_name}-instance-profile",
                                roles=[role.role_name]
                            )

        # Select between using the default VPC or use a specific subnet from config.json
        if config_data['network']['privateASubnetId'] and config_data['network']['vpcId']:
            # Create a reference to the VPC given in the config.json file
            vpc = ec2.Vpc.from_lookup(self, "VPC", vpc_id=config_data['network']['vpcId'])

            # Create an egress only security group for the instance during build ami
            security_group = ec2.SecurityGroup(self, "DCVAmiCreationSecurityGroup",
                                vpc=vpc,
                                description="SG default ports for DCV",
                                allow_all_outbound=True, #Egress all
                                disable_inline_rules=True
                            )

            # Create infrastructure configuration to supply instance type
            infra_config = imagebuilder.CfnInfrastructureConfiguration(self,
                                f"{image_pipeline_name}-infra-config",
                                name=f"{image_pipeline_name}-infra-config",
                                instance_types=[instance_type],
                                instance_profile_name=instance_profile.instance_profile_name,
                                subnet_id=config_data['network']['privateASubnetId'],
                                security_group_ids=[security_group.security_group_id]
                            )
        else: # Use default VPC
            # Create infrastructure configuration to supply instance type
            infra_config = imagebuilder.CfnInfrastructureConfiguration(self,
                                f"{image_pipeline_name}-infra-config",
                                name=f"{image_pipeline_name}-infra-config",
                                instance_types=[instance_type],
                                instance_profile_name=instance_profile.instance_profile_name,
                            )

        # Infrastructure config depends on instance profile to complete before beginning deployment.
        instance_profile.add_dependency(role.node.default_child)
        infra_config.add_dependency(instance_profile)

        # The imagebuilder pipeline
        imagebuilder.CfnImagePipeline(self,
            f"{image_pipeline_name}-pipeline",
            name=image_pipeline_name,
            image_recipe_arn=recipe.attr_arn,
            infrastructure_configuration_arn=infra_config.attr_arn
        )
