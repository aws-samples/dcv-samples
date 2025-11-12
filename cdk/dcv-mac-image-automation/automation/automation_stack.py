from aws_cdk import (
    Duration,
    Stack,
    aws_stepfunctions as sfn,
    aws_stepfunctions_tasks as tasks,
    aws_lambda as _lambda,
    aws_iam as iam,
    aws_ec2 as ec2,
    aws_logs as logs,
)
from constructs import Construct
import json
from .config_loader import ConfigLoader


class AutomationStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Load configuration
        self.config = ConfigLoader()
        self.config.validate_config()
        
        # Get configuration sections
        infra_config = self.config.get_infrastructure_config()
        ec2_config = self.config.get_ec2_config()
        lambda_config = self.config.get_lambda_config()
        step_function_config = self.config.get_step_function_config()
        mac_config = self.config.get('mac_monitoring', {})

        # DCV server build location (HTTPS URL or S3 URI)
        dcv_server_build_location = ec2_config['dcv_server_build_location']
        if not dcv_server_build_location:
            raise ValueError("DCV server build location must be specified in ec2.dcv_server_build_location config")
        
        # Detect if the location is an S3 URI or HTTPS URL
        is_s3_location = dcv_server_build_location.startswith('s3://')
        s3_bucket_arn = None
        
        if is_s3_location:
            # Parse S3 URI to get bucket name for IAM policy
            s3_parts = dcv_server_build_location.replace('s3://', '').split('/')
            s3_bucket_name = s3_parts[0]
            s3_bucket_arn = f"arn:aws:s3:::{s3_bucket_name}/*"     

        # Create VPC for EC2 instance
        vpc_config = infra_config['vpc']
        
        # Get the specific availability zone from EC2 placement config
        target_az = ec2_config.get('placement', {}).get('availability_zone')
        if not target_az:
            raise ValueError("Availability zone must be specified in ec2.placement.availability_zone config")
        
        # Extract region from availability zone (e.g., "us-east-2b" -> "us-east-2")
        target_region = target_az[:-1]  # Remove the last character (zone letter)
        
        # Create VPC with specific availability zone configuration
        vpc = ec2.Vpc(self, "AutomationVPC",
            availability_zones=[target_az],  # Specify the exact AZ
            nat_gateways=1,  # One NAT gateway for the single private subnet
            ip_addresses=ec2.IpAddresses.cidr(vpc_config['cidr']),
            subnet_configuration=[
                # Public subnet in the target AZ
                ec2.SubnetConfiguration(
                    name="PublicSubnet",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    cidr_mask=24
                ),
                # Private subnet in the target AZ  
                ec2.SubnetConfiguration(
                    name="PrivateSubnet", 
                    subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
                    cidr_mask=24
                )
            ]
        )

        # Create security group for EC2 instance
        security_group = ec2.SecurityGroup(self, "EC2SecurityGroup",
            vpc=vpc,
            description="Security group for automation EC2 instance",
            allow_all_outbound=True
        )

        # Add SSH access if configured
        sg_config = ec2_config['security_group']
        if sg_config.get('ssh_access', False):
            security_group.add_ingress_rule(
                ec2.Peer.ipv4(sg_config.get('ssh_cidr', '0.0.0.0/0')),
                ec2.Port.tcp(22),
                "SSH access"
            )
        
        # Add additional ports if configured
        for port_config in sg_config.get('additional_ports', []):
            port_num = port_config.get('port')
            if port_num is None:
                raise ValueError(f"Port number is required in security group additional_ports configuration: {port_config}")
            
            protocol = port_config.get('protocol', 'tcp')
            cidr = port_config.get('cidr', '0.0.0.0/0')
            description = port_config.get('description', f'{protocol.upper()} {port_num}')
            
            if protocol.lower() == 'tcp':
                security_group.add_ingress_rule(
                    ec2.Peer.ipv4(cidr),
                    ec2.Port.tcp(port_num),
                    description
                )
            elif protocol.lower() == 'udp':
                security_group.add_ingress_rule(
                    ec2.Peer.ipv4(cidr),
                    ec2.Port.udp(port_num),
                    description
                )

        # Create IAM role for Lambda functions with least-privilege permissions
        lambda_role = iam.Role(self, "LambdaExecutionRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaBasicExecutionRole")
            ]
        )

        # Add specific EC2 permissions required by Lambda functions
        lambda_role.add_to_policy(iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=[
                # Required by api_poller.py
                "ec2:DescribeMacModificationTasks",
                # Required by launch_ec2.py
                "ec2:RunInstances",
                "ec2:CreateTags",  # Required when launching instances with tags
                # Required by check_ec2_status.py
                "ec2:DescribeInstanceStatus",
                # Required by create_image.py
                "ec2:DescribeInstances",
                "ec2:CreateImage", 
                "ec2:StopInstances",
                "ec2:TerminateInstances",
                # Required by poll_ami_status.py
                "ec2:DescribeImages"
            ],
            resources=["*"]
        ))

        # Add specific SSM permissions required by Lambda functions
        lambda_role.add_to_policy(iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=[
                # Required by run_ssm_command.py
                "ssm:SendCommand",
                "ssm:GetCommandInvocation",
                "ssm:DescribeInstanceInformation",
                "ssm:ListCommandInvocations"
            ],
            resources=["*"]
        ))

        # Create IAM role for EC2 instance
        ec2_role = iam.Role(self, "EC2InstanceRole",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonSSMManagedInstanceCore")
            ]
        )

        # Add permission for Mac System Integrity Protection modification
        ec2_role.add_to_policy(iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=["ec2:CreateMacSystemIntegrityProtectionModificationTask"],
            resources=["*"]  # This permission typically requires broad resource access
        ))

        # Add permission to access DCV license S3 bucket
        ec2_role.add_to_policy(iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=["s3:GetObject"],
            resources=[f"arn:aws:s3:::dcv-license.{target_region}/*"]
        ))
        
        # Add permission to access DCV server build S3 bucket if location is S3 URI
        if is_s3_location and s3_bucket_arn:
            ec2_role.add_to_policy(iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["s3:GetObject"],
                resources=[s3_bucket_arn]
            ))

        # Add IAM PassRole permission required by launch_ec2.py
        lambda_role.add_to_policy(iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=["iam:PassRole"],
            resources=[ec2_role.role_arn],
            conditions={
                "StringEquals": {
                    "iam:PassedToService": "ec2.amazonaws.com"
                }
            }
        ))

        ec2_instance_profile = iam.InstanceProfile(self, "EC2InstanceProfile",
            role=ec2_role
        )

        # Get environment variables from config
        env_vars = self.config.get_runtime_environment_vars()
        
        # Validate private subnets exist before accessing
        if not vpc.private_subnets:
            raise ValueError("No private subnets available in VPC")
        
        env_vars.update({
            "VPC_ID": vpc.vpc_id,
            "SUBNET_ID": vpc.private_subnets[0].subnet_id,  # Use private subnet in the target AZ
            "SECURITY_GROUP_ID": security_group.security_group_id,
            "INSTANCE_PROFILE_ARN": ec2_instance_profile.instance_profile_arn,
            "MAC_POLLING_INTERVAL": str(mac_config.get('polling_interval_minutes', 5)),
        })

        # Create Lambda functions
        runtime = self._get_lambda_runtime(lambda_config['runtime'])
        
        lambda_functions = {
            'launch_ec2': self._create_lambda_function("LaunchEC2Lambda", "launch_ec2.handler", runtime, lambda_config, lambda_role, env_vars),
            'api_poller': self._create_lambda_function("MacSIPPollerLambda", "api_poller.handler", runtime, lambda_config, lambda_role, env_vars),
            'check_ec2_status': self._create_lambda_function("CheckEC2StatusLambda", "check_ec2_status.handler", runtime, lambda_config, lambda_role, env_vars),
            'run_ssm_command': self._create_lambda_function("RunSSMCommandLambda", "run_ssm_command.handler", runtime, lambda_config, lambda_role, env_vars),
            'create_image': self._create_lambda_function("CreateImageLambda", "create_image.handler", runtime, lambda_config, lambda_role, env_vars),
            'stop_instance': self._create_lambda_function("StopInstanceLambda", "stop_instance.handler", runtime, lambda_config, lambda_role, env_vars),
            'check_instance_stopped': self._create_lambda_function("CheckInstanceStoppedLambda", "check_instance_stopped.handler", runtime, lambda_config, lambda_role, env_vars),
            'poll_ami': self._create_lambda_function("PollAMIStatusLambda", "poll_ami_status.handler", runtime, lambda_config, lambda_role, env_vars),
            'terminate_instance': self._create_lambda_function("TerminateInstanceLambda", "terminate_instance.handler", runtime, lambda_config, lambda_role, env_vars)
        }
        
        # Extract individual Lambda functions for easier reference
        launch_ec2_lambda = lambda_functions['launch_ec2']
        api_poller_lambda = lambda_functions['api_poller']
        check_ec2_status_lambda = lambda_functions['check_ec2_status']
        run_ssm_command_lambda = lambda_functions['run_ssm_command']
        create_image_lambda = lambda_functions['create_image']
        stop_instance_lambda = lambda_functions['stop_instance']
        check_instance_stopped_lambda = lambda_functions['check_instance_stopped']
        poll_ami_lambda = lambda_functions['poll_ami']
        terminate_instance_lambda = lambda_functions['terminate_instance']

        # Define Step Function tasks
        launch_ec2_task = tasks.LambdaInvoke(self, "LaunchEC2Instance",
            lambda_function=launch_ec2_lambda,
            output_path="$.Payload"
        )

        wait_for_instance = sfn.Wait(self, "WaitForInstance",
            time=sfn.WaitTime.duration(Duration.minutes(step_function_config['wait_after_launch_minutes']))
        )

        # Task to check Mac SIP status for disabled state (first check)
        api_poller_task_disabled = tasks.LambdaInvoke(self, "CheckMacSIPStatusDisabled",
            lambda_function=api_poller_lambda,
            payload=sfn.TaskInput.from_object({
                "instance_id.$": "$.instance_id",
                "target_sip_status": "disabled"
            }),
            result_path="$.api_result"
        )

        # Task to check EC2 instance status (first check after SIP disabled)
        check_ec2_status_task_1 = tasks.LambdaInvoke(self, "CheckEC2StatusAfterSIPDisabled",
            lambda_function=check_ec2_status_lambda,
            payload=sfn.TaskInput.from_object({
                "instance_id.$": "$.instance_id"
            }),
            result_path="$.ec2_status_result"
        )

        # Task to run SSM command
        run_ssm_command_task = tasks.LambdaInvoke(self, "RunSSMCommand",
            lambda_function=run_ssm_command_lambda,
            payload=sfn.TaskInput.from_object({
                "instance_id.$": "$.instance_id",
                "ssm_retry_count.$": "$.ssm_retry_info.retry_count"
            }),
            result_path="$.ssm_result"
        )

        # Task to check Mac SIP status for enabled state (second check)
        api_poller_task_enabled = tasks.LambdaInvoke(self, "CheckMacSIPStatusEnabled",
            lambda_function=api_poller_lambda,
            payload=sfn.TaskInput.from_object({
                "instance_id.$": "$.instance_id",
                "target_sip_status": "enabled"
            }),
            result_path="$.api_result"
        )

        # Task to check EC2 instance status (second check after SIP enabled)
        check_ec2_status_task_2 = tasks.LambdaInvoke(self, "CheckEC2StatusAfterSIPEnabled",
            lambda_function=check_ec2_status_lambda,
            payload=sfn.TaskInput.from_object({
                "instance_id.$": "$.instance_id"
            }),
            result_path="$.ec2_status_result"
        )

        create_image_task = tasks.LambdaInvoke(self, "CreateAMI",
            lambda_function=create_image_lambda,
            output_path="$.Payload"
        )

        # Task to stop instance before AMI creation (optional)
        stop_instance_task = tasks.LambdaInvoke(self, "StopInstanceBeforeAMI",
            lambda_function=stop_instance_lambda,
            payload=sfn.TaskInput.from_object({
                "instance_id.$": "$.instance_id"
            }),
            result_path="$.stop_result"
        )

        # Task to check if instance is stopped
        check_instance_stopped_task = tasks.LambdaInvoke(self, "CheckInstanceStopped",
            lambda_function=check_instance_stopped_lambda,
            payload=sfn.TaskInput.from_object({
                "instance_id.$": "$.instance_id",
                "stop_requested.$": "$.stop_result.Payload.stop_requested"
            }),
            result_path="$.instance_stop_result"
        )

        # Task to poll AMI creation status
        poll_ami_task = tasks.LambdaInvoke(self, "PollAMIStatus",
            lambda_function=poll_ami_lambda,
            payload=sfn.TaskInput.from_object({
                "ami_id.$": "$.ami_id",
                "instance_id.$": "$.instance_id"
            }),
            result_path="$.ami_status_result"
        )

        # Task to terminate instance (optional)
        terminate_instance_task = tasks.LambdaInvoke(self, "TerminateInstance",
            lambda_function=terminate_instance_lambda,
            payload=sfn.TaskInput.from_object({
                "instance_id.$": "$.instance_id",
                "ami_id.$": "$.ami_id"
            }),
            result_path="$.terminate_result"
        )

        # Initialize retry counters for different phases
        initialize_retry_counters = sfn.Pass(self, "InitializeRetryCounters",
            parameters={
                "retry_info": {
                    "sip_disabled_retry_count": 0,
                    "ec2_status_retry_count": 0,
                    "ssm_retry_count": 0,
                    "sip_enabled_retry_count": 0,
                    "final_ec2_status_retry_count": 0,
                    "ami_polling_retry_count": 0,
                    "instance_stop_retry_count": 0
                },
                "instance_id.$": "$.instance_id"
            }
        )

        # Initialize SSM retry counter
        initialize_ssm_retry_counter = sfn.Pass(self, "InitializeSSMRetryCounter",
            parameters={
                "retry_info.$": "$.retry_info",
                "instance_id.$": "$.instance_id",
                "ssm_retry_info": {
                    "retry_count": 0
                }
            }
        )

        # Wait states for different retry scenarios
        retry_wait_sip_disabled = sfn.Wait(self, "WaitBeforeRetrySIPDisabled",
            time=sfn.WaitTime.duration(Duration.minutes(mac_config.get('polling_interval_minutes', 8)))
        )

        retry_wait_sip_enabled = sfn.Wait(self, "WaitBeforeRetrySIPEnabled",
            time=sfn.WaitTime.duration(Duration.minutes(mac_config.get('polling_interval_minutes', 5)))
        )

        retry_wait_ec2_first = sfn.Wait(self, "WaitBeforeRetryEC2StatusFirst",
            time=sfn.WaitTime.duration(Duration.minutes(2))
        )

        retry_wait_ec2_final = sfn.Wait(self, "WaitBeforeRetryEC2StatusFinal",
            time=sfn.WaitTime.duration(Duration.minutes(2))
        )

        retry_wait_ssm = sfn.Wait(self, "WaitBeforeRetrySSM",
            time=sfn.WaitTime.duration(Duration.minutes(1))
        )

        wait_ssm_status = sfn.Wait(self, "WaitForSSMStatus",
            time=sfn.WaitTime.duration(Duration.seconds(30))
        )

        retry_wait_ami = sfn.Wait(self, "WaitBeforeRetryAMIStatus",
            time=sfn.WaitTime.duration(Duration.seconds(30))
        )

        retry_wait_instance_stop = sfn.Wait(self, "WaitBeforeRetryInstanceStop",
            time=sfn.WaitTime.duration(Duration.seconds(30))
        )

        # Increment retry counters
        increment_sip_disabled_counter = sfn.Pass(self, "IncrementSIPDisabledCounter",
            parameters={
                "retry_info": {
                    "sip_disabled_retry_count.$": "States.MathAdd($.retry_info.sip_disabled_retry_count, 1)",
                    "ec2_status_retry_count.$": "$.retry_info.ec2_status_retry_count",
                    "ssm_retry_count.$": "$.retry_info.ssm_retry_count",
                    "sip_enabled_retry_count.$": "$.retry_info.sip_enabled_retry_count",
                    "final_ec2_status_retry_count.$": "$.retry_info.final_ec2_status_retry_count",
                    "ami_polling_retry_count": 0,
                    "instance_stop_retry_count": 0
                },
                "instance_id.$": "$.instance_id",
                "api_result.$": "$.api_result"
            }
        )

        increment_ec2_status_counter = sfn.Pass(self, "IncrementEC2StatusCounter",
            parameters={
                "retry_info": {
                    "sip_disabled_retry_count.$": "$.retry_info.sip_disabled_retry_count",
                    "ec2_status_retry_count.$": "States.MathAdd($.retry_info.ec2_status_retry_count, 1)",
                    "ssm_retry_count.$": "$.retry_info.ssm_retry_count",
                    "sip_enabled_retry_count.$": "$.retry_info.sip_enabled_retry_count",
                    "final_ec2_status_retry_count.$": "$.retry_info.final_ec2_status_retry_count",
                    "ami_polling_retry_count": 0,
                    "instance_stop_retry_count": 0
                },
                "instance_id.$": "$.instance_id",
                "ec2_status_result.$": "$.ec2_status_result"
            }
        )

        increment_sip_enabled_counter = sfn.Pass(self, "IncrementSIPEnabledCounter",
            parameters={
                "retry_info": {
                    "sip_disabled_retry_count.$": "$.retry_info.sip_disabled_retry_count",
                    "ec2_status_retry_count.$": "$.retry_info.ec2_status_retry_count",
                    "ssm_retry_count.$": "$.retry_info.ssm_retry_count",
                    "sip_enabled_retry_count.$": "States.MathAdd($.retry_info.sip_enabled_retry_count, 1)",
                    "final_ec2_status_retry_count.$": "$.retry_info.final_ec2_status_retry_count",
                    "ami_polling_retry_count": 0,
                    "instance_stop_retry_count": 0
                },
                "instance_id.$": "$.instance_id",
                "api_result.$": "$.api_result"
            }
        )

        increment_final_ec2_status_counter = sfn.Pass(self, "IncrementFinalEC2StatusCounter",
            parameters={
                "retry_info": {
                    "sip_disabled_retry_count.$": "$.retry_info.sip_disabled_retry_count",
                    "ec2_status_retry_count.$": "$.retry_info.ec2_status_retry_count",
                    "ssm_retry_count.$": "$.retry_info.ssm_retry_count",
                    "sip_enabled_retry_count.$": "$.retry_info.sip_enabled_retry_count",
                    "final_ec2_status_retry_count.$": "States.MathAdd($.retry_info.final_ec2_status_retry_count, 1)",
                    "ami_polling_retry_count": 0,
                    "instance_stop_retry_count": 0
                },
                "instance_id.$": "$.instance_id",
                "ec2_status_result.$": "$.ec2_status_result"
            }
        )

        increment_ami_polling_counter = sfn.Pass(self, "IncrementAMIPollingCounter",
            parameters={
                "retry_info": {
                    "ami_polling_retry_count.$": "States.MathAdd($.retry_info.ami_polling_retry_count, 1)"
                },
                "instance_id.$": "$.instance_id",
                "ami_id.$": "$.ami_id",
                "ami_status_result.$": "$.ami_status_result"
            }
        )

        increment_instance_stop_counter = sfn.Pass(self, "IncrementInstanceStopCounter",
            parameters={
                "retry_info": {
                    "sip_disabled_retry_count.$": "$.retry_info.sip_disabled_retry_count",
                    "ec2_status_retry_count.$": "$.retry_info.ec2_status_retry_count",
                    "ssm_retry_count.$": "$.retry_info.ssm_retry_count",
                    "sip_enabled_retry_count.$": "$.retry_info.sip_enabled_retry_count",
                    "final_ec2_status_retry_count.$": "$.retry_info.final_ec2_status_retry_count",
                    "ami_polling_retry_count": 0,
                    "instance_stop_retry_count.$": "States.MathAdd($.retry_info.instance_stop_retry_count, 1)"
                },
                "instance_id.$": "$.instance_id",
                "instance_stop_result.$": "$.instance_stop_result"
            }
        )

        # Initialize instance stop retry counter before stopping begins
        initialize_instance_stop_counter = sfn.Pass(self, "InitializeInstanceStopCounter",
            parameters={
                "retry_info": {
                    "sip_disabled_retry_count.$": "$.retry_info.sip_disabled_retry_count",
                    "ec2_status_retry_count.$": "$.retry_info.ec2_status_retry_count", 
                    "ssm_retry_count.$": "$.retry_info.ssm_retry_count",
                    "sip_enabled_retry_count.$": "$.retry_info.sip_enabled_retry_count",
                    "final_ec2_status_retry_count.$": "$.retry_info.final_ec2_status_retry_count",
                    "ami_polling_retry_count": 0,
                    "instance_stop_retry_count": 0
                },
                "instance_id.$": "$.instance_id"
            }
        )

        # Initialize AMI polling retry counter before polling begins
        initialize_ami_polling_counter = sfn.Pass(self, "InitializeAMIPollingCounter",
            parameters={
                "retry_info": {
                    "ami_polling_retry_count": 0
                },
                "instance_id.$": "$.instance_id",
                "ami_id.$": "$.ami_id"
            }
        )

        # Define choice conditions
        max_polling_attempts = mac_config.get('max_polling_attempts', 60)
        max_ec2_status_attempts = 20  # 2 minutes * 20 = 40 minutes max
        max_ssm_attempts = 5
        max_ami_polling_attempts = 60  # 30 seconds * 60 = 30 minutes max
        max_instance_stop_attempts = 20  # 30 seconds * 20 = 10 minutes max

        # SIP Disabled check choice
        sip_disabled_success_condition = sfn.Condition.string_equals("$.api_result.Payload.status", "success")
        sip_disabled_pending_condition = sfn.Condition.string_equals("$.api_result.Payload.status", "pending")
        sip_disabled_failed_condition = sfn.Condition.string_equals("$.api_result.Payload.status", "failed")
        sip_disabled_max_retries_exceeded = sfn.Condition.number_greater_than_equals("$.retry_info.sip_disabled_retry_count", max_polling_attempts)

        sip_disabled_retry_check = sfn.Choice(self, "CheckSIPDisabledRetryLimit")
        sip_disabled_retry_check.when(sip_disabled_max_retries_exceeded, 
            sfn.Fail(self, "SIPDisabledMaxRetriesExceeded",
                cause="Maximum SIP disabled polling attempts exceeded",
                error="SIPDisabledMaxRetriesError"
            )
        )
        sip_disabled_retry_check.otherwise(
            increment_sip_disabled_counter.next(retry_wait_sip_disabled.next(api_poller_task_disabled))
        )

        sip_disabled_choice = sfn.Choice(self, "CheckSIPDisabledResponse")
        sip_disabled_choice.when(sip_disabled_success_condition, check_ec2_status_task_1)
        sip_disabled_choice.when(sip_disabled_pending_condition, sip_disabled_retry_check)
        sip_disabled_choice.when(sip_disabled_failed_condition, 
            sfn.Fail(self, "SIPDisabledCheckFailed",
                cause="SIP disabled check failed",
                error="SIPDisabledError"
            )
        )
        sip_disabled_choice.otherwise(
            sfn.Fail(self, "SIPDisabledUnknownStatus",
                cause="SIP disabled check returned unknown status",
                error="SIPDisabledUnknownError"
            )
        )

        # EC2 Status check choice (first check)
        ec2_status_success_condition = sfn.Condition.string_equals("$.ec2_status_result.Payload.status", "success")
        ec2_status_pending_condition = sfn.Condition.string_equals("$.ec2_status_result.Payload.status", "pending")
        ec2_status_failed_condition = sfn.Condition.string_equals("$.ec2_status_result.Payload.status", "failed")
        ec2_status_max_retries_exceeded = sfn.Condition.number_greater_than_equals("$.retry_info.ec2_status_retry_count", max_ec2_status_attempts)

        ec2_status_retry_check = sfn.Choice(self, "CheckEC2StatusRetryLimit")
        ec2_status_retry_check.when(ec2_status_max_retries_exceeded,
            sfn.Fail(self, "EC2StatusMaxRetriesExceeded",
                cause="Maximum EC2 status check attempts exceeded",
                error="EC2StatusMaxRetriesError"
            )
        )
        ec2_status_retry_check.otherwise(
            increment_ec2_status_counter.next(retry_wait_ec2_first.next(check_ec2_status_task_1))
        )

        ec2_status_choice = sfn.Choice(self, "CheckEC2StatusResponse")
        ec2_status_choice.when(ec2_status_success_condition, initialize_ssm_retry_counter)
        ec2_status_choice.when(ec2_status_pending_condition, ec2_status_retry_check)
        ec2_status_choice.when(ec2_status_failed_condition,
            sfn.Fail(self, "EC2StatusCheckFailed",
                cause="EC2 status check failed",
                error="EC2StatusError"
            )
        )
        ec2_status_choice.otherwise(
            sfn.Fail(self, "EC2StatusUnknownStatus",
                cause="EC2 status check returned unknown status",
                error="EC2StatusUnknownError"
            )
        )

        # SSM Command choice
        ssm_success_condition = sfn.Condition.string_equals("$.ssm_result.Payload.status", "success")
        ssm_pending_condition = sfn.Condition.string_equals("$.ssm_result.Payload.status", "pending")
        ssm_retry_condition = sfn.Condition.string_equals("$.ssm_result.Payload.status", "retry")
        ssm_failed_condition = sfn.Condition.string_equals("$.ssm_result.Payload.status", "failed")
        ssm_max_retries_exceeded = sfn.Condition.number_greater_than_equals("$.ssm_retry_info.retry_count", max_ssm_attempts)

        ssm_retry_check = sfn.Choice(self, "CheckSSMRetryLimit")
        ssm_retry_check.when(ssm_max_retries_exceeded,
            sfn.Fail(self, "SSMMaxRetriesExceeded",
                cause="Maximum SSM command attempts exceeded",
                error="SSMMaxRetriesError"
            )
        )
        ssm_retry_check.otherwise(retry_wait_ssm.next(run_ssm_command_task))

        ssm_choice = sfn.Choice(self, "CheckSSMResponse")
        ssm_choice.when(ssm_success_condition, 
            sfn.Pass(self, "ResetSIPEnabledRetryCounter",
                parameters={
                    "retry_info": {
                        "sip_disabled_retry_count.$": "$.retry_info.sip_disabled_retry_count",
                        "ec2_status_retry_count": 0,
                        "ssm_retry_count.$": "$.retry_info.ssm_retry_count",
                        "sip_enabled_retry_count": 0,
                        "final_ec2_status_retry_count": 0
                    },
                    "instance_id.$": "$.instance_id"
                }
            ).next(api_poller_task_enabled)
        )
        ssm_choice.when(ssm_pending_condition, wait_ssm_status.next(
            tasks.LambdaInvoke(self, "CheckSSMCommandStatus",
                lambda_function=run_ssm_command_lambda,
                payload=sfn.TaskInput.from_object({
                    "instance_id.$": "$.instance_id",
                    "command_id.$": "$.ssm_result.Payload.command_id",
                    "ssm_retry_count.$": "$.ssm_retry_info.retry_count"
                }),
                result_path="$.ssm_result"
            ).next(ssm_choice)
        ))
        ssm_choice.when(ssm_retry_condition, ssm_retry_check)
        ssm_choice.when(ssm_failed_condition,
            sfn.Fail(self, "SSMCommandFailed",
                cause="SSM command execution failed",
                error="SSMCommandError"
            )
        )
        ssm_choice.otherwise(
            sfn.Fail(self, "SSMUnknownStatus",
                cause="SSM command returned unknown status",
                error="SSMUnknownError"
            )
        )

        # SIP Enabled check choice
        sip_enabled_success_condition = sfn.Condition.string_equals("$.api_result.Payload.status", "success")
        sip_enabled_pending_condition = sfn.Condition.string_equals("$.api_result.Payload.status", "pending")
        sip_enabled_failed_condition = sfn.Condition.string_equals("$.api_result.Payload.status", "failed")
        sip_enabled_max_retries_exceeded = sfn.Condition.number_greater_than_equals("$.retry_info.sip_enabled_retry_count", max_polling_attempts)

        sip_enabled_retry_check = sfn.Choice(self, "CheckSIPEnabledRetryLimit")
        sip_enabled_retry_check.when(sip_enabled_max_retries_exceeded,
            sfn.Fail(self, "SIPEnabledMaxRetriesExceeded",
                cause="Maximum SIP enabled polling attempts exceeded",
                error="SIPEnabledMaxRetriesError"
            )
        )
        sip_enabled_retry_check.otherwise(
            increment_sip_enabled_counter.next(retry_wait_sip_enabled.next(api_poller_task_enabled))
        )

        sip_enabled_choice = sfn.Choice(self, "CheckSIPEnabledResponse")
        sip_enabled_choice.when(sip_enabled_success_condition, 
            sfn.Pass(self, "ResetFinalEC2RetryCounter",
                parameters={
                    "retry_info": {
                        "sip_disabled_retry_count.$": "$.retry_info.sip_disabled_retry_count",
                        "ec2_status_retry_count.$": "$.retry_info.ec2_status_retry_count",
                        "ssm_retry_count.$": "$.retry_info.ssm_retry_count",
                        "sip_enabled_retry_count.$": "$.retry_info.sip_enabled_retry_count",
                        "final_ec2_status_retry_count": 0
                    },
                    "instance_id.$": "$.instance_id"
                }
            ).next(check_ec2_status_task_2)
        )
        sip_enabled_choice.when(sip_enabled_pending_condition, sip_enabled_retry_check)
        sip_enabled_choice.when(sip_enabled_failed_condition,
            sfn.Fail(self, "SIPEnabledCheckFailed",
                cause="SIP enabled check failed",
                error="SIPEnabledError"
            )
        )
        sip_enabled_choice.otherwise(
            sfn.Fail(self, "SIPEnabledUnknownStatus",
                cause="SIP enabled check returned unknown status",
                error="SIPEnabledUnknownError"
            )
        )

        # Final EC2 Status check choice
        final_ec2_status_success_condition = sfn.Condition.string_equals("$.ec2_status_result.Payload.status", "success")
        final_ec2_status_pending_condition = sfn.Condition.string_equals("$.ec2_status_result.Payload.status", "pending")
        final_ec2_status_failed_condition = sfn.Condition.string_equals("$.ec2_status_result.Payload.status", "failed")
        final_ec2_status_max_retries_exceeded = sfn.Condition.number_greater_than_equals("$.retry_info.final_ec2_status_retry_count", max_ec2_status_attempts)

        final_ec2_status_retry_check = sfn.Choice(self, "CheckFinalEC2StatusRetryLimit")
        final_ec2_status_retry_check.when(final_ec2_status_max_retries_exceeded,
            sfn.Fail(self, "FinalEC2StatusMaxRetriesExceeded",
                cause="Maximum final EC2 status check attempts exceeded",
                error="FinalEC2StatusMaxRetriesError"
            )
        )
        final_ec2_status_retry_check.otherwise(
            increment_final_ec2_status_counter.next(retry_wait_ec2_final.next(check_ec2_status_task_2))
        )

        final_ec2_status_choice = sfn.Choice(self, "CheckFinalEC2StatusResponse")
        final_ec2_status_choice.when(final_ec2_status_success_condition, initialize_instance_stop_counter)
        final_ec2_status_choice.when(final_ec2_status_pending_condition, final_ec2_status_retry_check)
        final_ec2_status_choice.when(final_ec2_status_failed_condition,
            sfn.Fail(self, "FinalEC2StatusCheckFailed",
                cause="Final EC2 status check failed",
                error="FinalEC2StatusError"
            )
        )
        final_ec2_status_choice.otherwise(
            sfn.Fail(self, "FinalEC2StatusUnknownStatus",
                cause="Final EC2 status check returned unknown status",
                error="FinalEC2StatusUnknownError"
            )
        )

        # AMI polling choice
        ami_success_condition = sfn.Condition.string_equals("$.ami_status_result.Payload.status", "success")
        ami_pending_condition = sfn.Condition.string_equals("$.ami_status_result.Payload.status", "pending")
        ami_failed_condition = sfn.Condition.string_equals("$.ami_status_result.Payload.status", "failed")
        ami_max_retries_exceeded = sfn.Condition.number_greater_than_equals("$.retry_info.ami_polling_retry_count", max_ami_polling_attempts)

        ami_retry_check = sfn.Choice(self, "CheckAMIPollingRetryLimit")
        ami_retry_check.when(ami_max_retries_exceeded,
            sfn.Fail(self, "AMIPollingMaxRetriesExceeded",
                cause="Maximum AMI polling attempts exceeded",
                error="AMIPollingMaxRetriesError"
            )
        )
        ami_retry_check.otherwise(
            increment_ami_polling_counter.next(retry_wait_ami.next(poll_ami_task))
        )

        ami_choice = sfn.Choice(self, "CheckAMIStatusResponse")
        ami_choice.when(ami_success_condition, terminate_instance_task)
        ami_choice.when(ami_pending_condition, ami_retry_check)
        ami_choice.when(ami_failed_condition,
            sfn.Fail(self, "AMICreationFailed",
                cause="AMI creation failed",
                error="AMICreationError"
            )
        )
        ami_choice.otherwise(
            sfn.Fail(self, "AMIUnknownStatus",
                cause="AMI status check returned unknown status",
                error="AMIUnknownError"
            )
        )

        # Instance stop choice
        instance_stop_success_condition = sfn.Condition.string_equals("$.instance_stop_result.Payload.status", "success")
        instance_stop_pending_condition = sfn.Condition.string_equals("$.instance_stop_result.Payload.status", "pending")
        instance_stop_failed_condition = sfn.Condition.string_equals("$.instance_stop_result.Payload.status", "failed")
        instance_stop_max_retries_exceeded = sfn.Condition.number_greater_than_equals("$.retry_info.instance_stop_retry_count", max_instance_stop_attempts)

        instance_stop_retry_check = sfn.Choice(self, "CheckInstanceStopRetryLimit")
        instance_stop_retry_check.when(instance_stop_max_retries_exceeded,
            sfn.Fail(self, "InstanceStopMaxRetriesExceeded",
                cause="Maximum instance stop check attempts exceeded",
                error="InstanceStopMaxRetriesError"
            )
        )
        instance_stop_retry_check.otherwise(
            increment_instance_stop_counter.next(retry_wait_instance_stop.next(check_instance_stopped_task))
        )

        instance_stop_choice = sfn.Choice(self, "CheckInstanceStopResponse")
        instance_stop_choice.when(instance_stop_success_condition, create_image_task)
        instance_stop_choice.when(instance_stop_pending_condition, instance_stop_retry_check)
        instance_stop_choice.when(instance_stop_failed_condition,
            sfn.Fail(self, "InstanceStopCheckFailed",
                cause="Instance stop check failed",
                error="InstanceStopError"
            )
        )
        instance_stop_choice.otherwise(
            sfn.Fail(self, "InstanceStopUnknownStatus",
                cause="Instance stop check returned unknown status",
                error="InstanceStopUnknownError"
            )
        )

        # Choice to determine if we should terminate instance or finish workflow
        should_terminate_choice = sfn.Choice(self, "ShouldTerminateInstance")
        terminate_requested_condition = sfn.Condition.boolean_equals("$.terminate_instance", True)
        
        # Success state for when termination is not requested
        workflow_complete = sfn.Succeed(self, "WorkflowCompleteAMICreated",
            comment="AMI creation completed successfully. Instance termination not requested."
        )
        
        should_terminate_choice.when(terminate_requested_condition, initialize_ami_polling_counter)
        should_terminate_choice.otherwise(workflow_complete)

        # Connect the tasks to choices
        api_poller_task_disabled.next(sip_disabled_choice)
        check_ec2_status_task_1.next(ec2_status_choice)
        initialize_ssm_retry_counter.next(run_ssm_command_task)
        run_ssm_command_task.next(ssm_choice)
        api_poller_task_enabled.next(sip_enabled_choice)
        check_ec2_status_task_2.next(final_ec2_status_choice)
        initialize_instance_stop_counter.next(stop_instance_task)
        stop_instance_task.next(check_instance_stopped_task)
        check_instance_stopped_task.next(instance_stop_choice)
        create_image_task.next(should_terminate_choice)
        initialize_ami_polling_counter.next(poll_ami_task)
        poll_ami_task.next(ami_choice)
        terminate_instance_task.next(
            sfn.Succeed(self, "WorkflowCompleteWithTermination",
                comment="AMI creation completed and instance terminated successfully."
            )
        )

        # Define the Step Function workflow
        definition = launch_ec2_task.next(
            wait_for_instance.next(
                initialize_retry_counters.next(api_poller_task_disabled)
            )
        )

        # Create Step Function
        state_machine = sfn.StateMachine(self, step_function_config['name'],
            definition_body=sfn.DefinitionBody.from_chainable(definition),
            timeout=Duration.hours(infra_config['timeouts']['step_function_hours']),
            logs=sfn.LogOptions(
                destination=logs.LogGroup(self, "StateMachineLogGroup"),
                level=getattr(sfn.LogLevel, step_function_config['log_level'])
            )
        )

        # Output the Step Function ARN
        self.add_outputs({
            "StateMachineArn": state_machine.state_machine_arn,
            "VpcId": vpc.vpc_id,
            "SecurityGroupId": security_group.security_group_id
        })

    def _get_lambda_runtime(self, runtime_str: str):
        """Convert runtime string to CDK Runtime object"""
        return getattr(_lambda.Runtime, runtime_str.upper().replace('PYTHON3', 'PYTHON_3').replace('.', '_'))
    
    def _create_lambda_function(self, construct_id: str, handler: str, runtime, lambda_config: dict, role, env_vars: dict):
        """Create a Lambda function with common configuration"""
        return _lambda.Function(self, construct_id,
            runtime=runtime,
            handler=handler,
            code=_lambda.Code.from_asset("lambda"),
            timeout=Duration.minutes(lambda_config['timeout_minutes']),
            memory_size=lambda_config['memory_mb'],
            role=role,
            environment=env_vars
        )

    def add_outputs(self, outputs: dict):
        """Helper method to add stack outputs"""
        from aws_cdk import CfnOutput
        for key, value in outputs.items():
            CfnOutput(self, key, value=value)