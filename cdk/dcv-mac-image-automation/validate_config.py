#!/usr/bin/env python3
"""
Configuration validation script for AWS EC2 MAC DCV Automation
Run this script to validate your config.json file before deployment
"""

import json
import sys
from pathlib import Path
from automation.config_loader import ConfigLoader

def validate_config_file():
    """Validate the configuration file and print detailed results"""
    
    print("  AWS EC2 Automation Configuration Validator")
    print("=" * 50)
    
    config_path = Path("config.json")
    if not config_path.exists():
        print("  Error: config.json file not found!")
        print("Please ensure config.json exists in the project root directory.")
        return False
    
    try:
        # Load and validate configuration
        config = ConfigLoader()
        config.validate_config()
        
        print("  Configuration validation passed!")
        print()
        
        # Display configuration summary
        print("  Configuration Summary:")
        print("-" * 30)
        
        # EC2 Configuration
        print("🖥️  EC2 Configuration:")
        print(f"   AMI ID: {config.get('ec2.ami_id')}")
        print(f"   Instance Type: {config.get('ec2.instance_type')}")
        print(f"   Key Name: {config.get('ec2.key_name') or 'Not configured'}")
        print(f"   EC2 User Password: {'Configured' if config.get('ec2.ec2_user_password') else 'Not configured'}")
        print(f"   Automatic DCV Session: {config.get('ec2.automatic_ec2-user_dcv_session_creation', 'Not configured')}")
        print(f"   SSH Access: {config.get('ec2.security_group.ssh_access')}")
        
        # Additional ports configuration
        additional_ports = config.get('ec2.security_group.additional_ports', [])
        if additional_ports:
            print(f"   Additional Ports: {len(additional_ports)} port(s) configured")
            for port in additional_ports:
                print(f"     - Port {port.get('port')}/{port.get('protocol', 'tcp')} from {port.get('cidr', 'unknown')}")
        
        # Mac-specific placement configuration
        instance_type = config.get('ec2.instance_type', '')
        if instance_type.startswith('mac'):
            print("    Mac Placement:")
            print(f"     Tenancy: {config.get('ec2.placement.tenancy', 'Not configured')}")
            print(f"     Host ID: {config.get('ec2.placement.host_id') or 'Not specified'}")
            print(f"     Availability Zone: {config.get('ec2.placement.availability_zone') or 'Not specified'}")
        print()
        
        # Mac SIP Monitoring Configuration
        print("   Mac SIP Monitoring Configuration:")
        print(f"   Polling Interval: {config.get('mac_monitoring.polling_interval_minutes')} minutes")
        print(f"   Max Polling Attempts: {config.get('mac_monitoring.max_polling_attempts')}")
        print(f"   Timeout: {config.get('mac_monitoring.timeout_hours')} hours")
        
        # Task filters
        task_filters = config.get('mac_monitoring.task_filters', {})
        if task_filters:
            print("    Task Filters:")
            for key, value in task_filters.items():
                if isinstance(value, list):
                    print(f"     {key}: {', '.join(value)}")
                else:
                    print(f"     {key}: {value}")
        print()
        
        # AMI Configuration
        print("  AMI Configuration:")
        print(f"   Naming Pattern: {config.get('ami.naming_pattern')}")
        print(f"   Description Pattern: {config.get('ami.description_pattern', 'Not configured')}")
        print(f"   No Reboot: {config.get('ami.no_reboot')}")
        
        # AMI Tags
        ami_tags = config.get('ami.tags', {})
        if ami_tags:
            print(f"   AMI Tags: {len(ami_tags)} tag(s)")
            for key, value in ami_tags.items():
                print(f"     {key}: {value}")
        
        print(f"   Options:")
        print(f"     Stop Instance Before Creation: {config.get('ami.options.stop_instance_before_creation')}")
        print(f"     Wait for Completion: {config.get('ami.options.wait_for_completion')}")
        print(f"     Terminate After Creation: {config.get('ami.options.terminate_instance_after_creation')}")
        print()
        
        # Infrastructure Configuration
        print("🏗️  Infrastructure Configuration:")
        print(f"   VPC CIDR: {config.get('infrastructure.vpc.cidr')}")
        print(f"   Max AZs: {config.get('infrastructure.vpc.max_azs', 'Not configured')}")
        print(f"   NAT Gateways: {config.get('infrastructure.vpc.nat_gateways', 'Not configured')}")
        
        # Infrastructure timeouts
        print(f"   Timeouts:")
        print(f"     Instance Launch: {config.get('infrastructure.timeouts.instance_launch_minutes', 'Default')} minutes")
        print(f"     Instance Running Wait: {config.get('infrastructure.timeouts.instance_running_wait_minutes', 'Default')} minutes")
        print(f"     AMI Creation: {config.get('infrastructure.timeouts.ami_creation_minutes', 'Default')} minutes")
        print(f"     Step Function: {config.get('infrastructure.timeouts.step_function_hours', 'Default')} hours")
        print()
        
        # SSM Configuration
        ssm_config = config.get('ssm')
        if ssm_config:
            print("SSM Configuration:")
            print(f"   Working Directory: {ssm_config.get('working_directory', '/tmp')}")
            print(f"   Timeout: {ssm_config.get('timeout_seconds', 300)} seconds")
            print(f"   Max Retries: {ssm_config.get('max_retries', 5)}")
            print()
        
        # Lambda Configuration
        print("⚡ Lambda Configuration:")
        print(f"   Runtime: {config.get('lambda.runtime')}")
        print(f"   Timeout: {config.get('lambda.timeout_minutes')} minutes")
        print(f"   Memory: {config.get('lambda.memory_mb')} MB")
        
        # Lambda environment variables
        lambda_env_vars = config.get('lambda.environment_variables', {})
        if lambda_env_vars:
            print(f"   Environment Variables:")
            for key, value in lambda_env_vars.items():
                print(f"     {key}: {value}")
        print()
        
        # Step Function Configuration
        print("Step Function Configuration:")
        print(f"   Name: {config.get('step_function.name')}")
        print(f"   Wait After Launch: {config.get('step_function.wait_after_launch_minutes')} minutes")
        print(f"   Log Level: {config.get('step_function.log_level')}")
        print()
        
        # Warnings and recommendations
        print("⚠️  Warnings and Recommendations:")
        print("-" * 35)
        
        warnings = []
        
        # Check for Mac-specific configuration
        
        # Check Mac instance placement configuration
        instance_type = config.get('ec2.instance_type', '')
        if instance_type.startswith('mac'):
            # Validate that only Apple Silicon instances are supported
            if instance_type.startswith('mac1'):
                raise ValueError(f"Mac1 instance type '{instance_type}' is not supported. This automation requires Apple Silicon instances for DCV compatibility.")
            
            placement_tenancy = config.get('ec2.placement.tenancy')
            if placement_tenancy != 'host':
                warnings.append("Mac instances require dedicated host tenancy (placement.tenancy should be 'host')")
            
            host_id = config.get('ec2.placement.host_id')
            if not host_id:
                warnings.append("Consider specifying a dedicated host ID for Mac instances (placement.host_id)")
            
            az = config.get('ec2.placement.availability_zone')
            if not az:
                warnings.append("Consider specifying availability zone for Mac instances (placement.availability_zone)")
            
            # Check for Mac-specific DCV configuration
            ec2_user_password = config.get('ec2.ec2_user_password')
            if not ec2_user_password:
                warnings.append("EC2 user password is required for Mac instances with DCV automation (ec2.ec2_user_password)")
            else:
                # Check password length
                if len(ec2_user_password) > 16:
                    warnings.append("EC2 user password should be less than 16 characters long. SIP modification will fail if the password is greater than 16 characters long.")
                
                # Check for shell metacharacters that could cause command injection
                dangerous_chars = ['"', "'", '`', '$', '\\', ';', '|', '&', '\n', '\r']
                found_chars = [char for char in dangerous_chars if char in ec2_user_password]
                if found_chars:
                    char_display = ', '.join(repr(char) for char in found_chars)
                    raise ValueError(f"EC2 user password contains dangerous shell metacharacters: {char_display}. These characters could cause command injection vulnerabilities.")
            
            # Check DCV session configuration
            dcv_session = config.get('ec2.automatic_ec2-user_dcv_session_creation')
            if dcv_session is None:
                warnings.append("Consider configuring automatic DCV session creation (ec2.automatic_ec2-user_dcv_session_creation)")
        elif instance_type and not instance_type.startswith('mac'):
            # Non-Mac instances are not supported
            raise ValueError(f"Non-Mac instance type '{instance_type}' is not supported. This automation is specifically designed for Apple Silicon instances.")
        
        # Security warnings
        if config.get('ec2.key_name') is None:
            warnings.append("No EC2 key pair configured (SSH access will not be available)")
        
        if config.get('ec2.security_group.ssh_access') and config.get('ec2.security_group.ssh_cidr') == '0.0.0.0/0':
            warnings.append("SSH access is open to all IPs (0.0.0.0/0) - consider restricting")
        
        # Check additional ports security
        additional_ports = config.get('ec2.security_group.additional_ports', [])
        for port in additional_ports:
            if port.get('cidr') == '0.0.0.0/0':
                warnings.append(f"Port {port.get('port')} is open to all IPs (0.0.0.0/0) - consider restricting")
        
        # Configuration value warnings
        if config.get('mac_monitoring.polling_interval_minutes', 5) < 1:
            warnings.append("Mac polling interval should be at least 1 minute")
        
        if config.get('mac_monitoring.max_polling_attempts', 24) > 100:
            warnings.append("Max polling attempts is very high - consider reducing to avoid excessive costs")
        
        if config.get('ami.options.terminate_instance_after_creation'):
            warnings.append("Instance will be terminated after AMI creation (ensure this is intended)")
        
        # SSM configuration warnings
        ssm_timeout = config.get('ssm.timeout_seconds', 300)
        if ssm_timeout < 60:
            warnings.append("SSM timeout is very short - commands may fail due to insufficient time")
        
        # Lambda configuration warnings
        lambda_timeout = config.get('lambda.timeout_minutes', 5)
        if lambda_timeout < 3:
            warnings.append("Lambda timeout is very short - functions may timeout during execution")
        
        lambda_memory = config.get('lambda.memory_mb', 256)
        if lambda_memory < 128:
            warnings.append("Lambda memory is very low - consider increasing for better performance")
        
        # Infrastructure warnings
        vpc_cidr = config.get('infrastructure.vpc.cidr', '')
        if vpc_cidr and not vpc_cidr.startswith('10.'):
            warnings.append("Consider using private IP ranges (10.x.x.x) for VPC CIDR")
        
        if not warnings:
            print("✅ No warnings - configuration looks good!")
        else:
            for warning in warnings:
                print(f"   ⚠️  {warning}")
        
        print()
        print("🚀 Configuration is ready for deployment!")
        print("   Run './deploy.sh' to deploy the automation")
        
        return True
        
    except FileNotFoundError:
        print("❌ Error: config.json file not found!")
        return False
    except json.JSONDecodeError as e:
        print(f"❌ Error: Invalid JSON in config.json - {e}")
        return False
    except ValueError as e:
        print(f"❌ Error: Configuration validation failed - {e}")
        return False
    except Exception as e:
        print(f"❌ Error: Unexpected error - {e}")
        return False

def show_config_template():
    """Show a template configuration with explanations"""
    
    print("\n" + "=" * 60)
    print("📝 Configuration Template and Field Explanations")
    print("=" * 60)
    
    explanations = {
        # EC2 Configuration
        "ec2.ami_id": "AWS AMI ID to use for launching Mac2 instances",
        "ec2.instance_type": "EC2 Mac2 instance type (mac2-m1.metal, mac2-m2.metal, mac2-m2pro.metal)",
        "ec2.key_name": "EC2 key pair name for SSH access (optional)",
        "ec2.ec2_user_password": "Password for ec2-user account (required for Mac DCV automation)",
        "ec2.automatic_ec2-user_dcv_session_creation": "Enable automatic DCV session creation (true/false)",
        "ec2.placement.tenancy": "Instance tenancy (use 'host' for Mac instances)",
        "ec2.placement.host_id": "Dedicated host ID for Mac instances",
        "ec2.placement.availability_zone": "Specific availability zone (e.g., us-east-1a)",
        "ec2.security_group.ssh_access": "Enable SSH access (true/false)",
        "ec2.security_group.ssh_cidr": "CIDR block for SSH access (e.g., 10.0.0.0/8)",
        "ec2.security_group.additional_ports": "List of additional ports to open",
        "ec2.tags": "Tags to apply to EC2 instances",
        
        # Mac Monitoring Configuration
        "mac_monitoring.polling_interval_minutes": "Minutes between SIP status checks",
        "mac_monitoring.max_polling_attempts": "Maximum number of polling attempts",
        "mac_monitoring.timeout_hours": "Total timeout for SIP modification process",
        "mac_monitoring.task_filters": "Filters for Mac modification tasks",
        
        # AMI Configuration
        "ami.naming_pattern": "Pattern for AMI names (supports {instance_id}, {timestamp})",
        "ami.description_pattern": "Pattern for AMI descriptions",
        "ami.no_reboot": "Create AMI without rebooting instance (true/false)",
        "ami.tags": "Tags to apply to created AMIs",
        "ami.options.stop_instance_before_creation": "Stop instance before creating AMI",
        "ami.options.wait_for_completion": "Wait for AMI creation to complete",
        "ami.options.terminate_instance_after_creation": "Terminate instance after AMI creation",
        
        # Infrastructure Configuration
        "infrastructure.vpc.cidr": "CIDR block for the VPC (e.g., 10.0.0.0/16)",
        "infrastructure.vpc.max_azs": "Maximum number of availability zones",
        "infrastructure.vpc.nat_gateways": "Number of NAT gateways",
        "infrastructure.timeouts.instance_launch_minutes": "Timeout for instance launch",
        "infrastructure.timeouts.instance_running_wait_minutes": "Wait time for instance to be running",
        "infrastructure.timeouts.ami_creation_minutes": "Timeout for AMI creation",
        "infrastructure.timeouts.step_function_hours": "Overall Step Function timeout",
        
        # SSM Configuration
        "ssm.working_directory": "Working directory for SSM commands (e.g., /tmp)",
        "ssm.timeout_seconds": "Timeout for individual SSM commands",
        "ssm.max_retries": "Maximum number of SSM command retries",
        
        # Lambda Configuration
        "lambda.runtime": "Lambda runtime version (e.g., python3.11)",
        "lambda.timeout_minutes": "Lambda function timeout in minutes",
        "lambda.memory_mb": "Lambda function memory in MB",
        "lambda.environment_variables": "Environment variables for Lambda functions",
        
        # Step Function Configuration
        "step_function.name": "Name of the Step Function state machine",
        "step_function.wait_after_launch_minutes": "Time to wait after launching instance",
        "step_function.log_level": "Step Function logging level (ALL, ERROR, FATAL, OFF)"
    }
    
    print("\n🔧 Core Configuration Fields:")
    print("-" * 30)
    
    # Group by category for better readability
    categories = {
        "EC2": [k for k in explanations.keys() if k.startswith("ec2.")],
        "Mac Monitoring": [k for k in explanations.keys() if k.startswith("mac_monitoring.")],
        "AMI": [k for k in explanations.keys() if k.startswith("ami.")],
        "Infrastructure": [k for k in explanations.keys() if k.startswith("infrastructure.")],
        "SSM": [k for k in explanations.keys() if k.startswith("ssm.")],
        "Lambda": [k for k in explanations.keys() if k.startswith("lambda.")],
        "Step Function": [k for k in explanations.keys() if k.startswith("step_function.")]
    }
    
    for category, keys in categories.items():
        print(f"\n📂 {category}:")
        for key in keys:
            print(f"   {key:<45} : {explanations[key]}")
    
    print(f"\n💡 Tips:")
    print(f"   - Use 'python3 validate_config.py' to validate your configuration")
    print(f"   - Only Mac2 (Apple Silicon) instances are supported: mac2-m1.metal, mac2-m2.metal, mac2-m2pro.metal")
    print(f"   - Mac instances require dedicated host tenancy and host_id")
    print(f"   - Set ec2_user_password for DCV automation to work properly (max 16 characters)")
    print(f"   - Use private IP ranges (10.x.x.x) for VPC CIDR blocks")

def main():
    """Main validation function"""
    
    if len(sys.argv) > 1 and sys.argv[1] in ['--help', '-h', 'help']:
        print("AWS EC2 Automation Configuration Validator")
        print()
        print("Usage:")
        print("  python3 validate_config.py          - Validate config.json")
        print("  python3 validate_config.py --help   - Show this help")
        print("  python3 validate_config.py template - Show configuration field explanations")
        return
    
    if len(sys.argv) > 1 and sys.argv[1] == 'template':
        show_config_template()
        return
    
    success = validate_config_file()
    
    if not success:
        print("\n💡 Tips:")
        print("   - Check config.json syntax with a JSON validator")
        print("   - Ensure all required fields are present")
        print("   - Run 'python3 validate_config.py template' to see field explanations")
        sys.exit(1)
    else:
        sys.exit(0)

if __name__ == "__main__":
    main()