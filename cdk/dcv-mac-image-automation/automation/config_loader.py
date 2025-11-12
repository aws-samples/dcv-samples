"""
Configuration loader module for AWS EC2 Automation
Handles loading and validation of configuration from config.json
"""

import json
import os
from typing import Dict, Any, Optional
from pathlib import Path


class ConfigLoader:
    """Handles loading and accessing configuration parameters"""
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize the config loader
        
        Args:
            config_path: Path to config.json file. If None, looks in project root.
        """
        if config_path is None:
            # Look for config.json in the project root
            project_root = Path(__file__).parent.parent
            config_path = project_root / "config.json"
        
        # Validate and resolve the config path to prevent directory traversal
        config_path = Path(config_path).resolve()
        project_root = Path(__file__).parent.parent.resolve()

        # Ensure the config path is within the project directory
        try:
            config_path.relative_to(project_root)
        except ValueError:
            raise ValueError(f"Config path outside project directory: {config_path}")

        self.config_path = config_path
        self._config = self._load_config()
        self._cached_config_json = None
        self._cache_dirty = False
    
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from JSON file"""
        try:
            with open(self.config_path, 'r') as f:
                config = json.load(f)
            return config
        except FileNotFoundError:
            raise FileNotFoundError(f"Configuration file not found: {self.config_path}")
        except PermissionError:
            raise PermissionError(f"Permission denied accessing config file: {self.config_path}")
        except OSError as e:
            raise OSError(f"OSError reading config file: {self.config_path}, {e}")
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in configuration file: {e}")
    
    def get(self, key_path: str, default: Any = None) -> Any:
        """
        Get a configuration value using dot notation
        
        Args:
            key_path: Dot-separated path to the configuration value (e.g., 'ec2.instance_type')
            default: Default value if key is not found
            
        Returns:
            Configuration value or default
            
        Example:
            config.get('ec2.instance_type')  # Returns 't3.micro'
            config.get('api.endpoint')       # Returns API endpoint URL
        """
        keys = key_path.split('.')
        value = self._config
        
        try:
            for key in keys:
                value = value[key]
            return value
        except (KeyError, TypeError):
            return default
    
    def get_ec2_config(self) -> Dict[str, Any]:
        """Get all EC2-related configuration"""
        config = self.get('ec2')
        if config is None:
            raise ValueError("Missing required 'ec2' configuration section")
        return config
    
    def get_mac_monitoring_config(self) -> Dict[str, Any]:
        """Get all Mac monitoring-related configuration"""
        config = self.get('mac_monitoring')
        if config is None:
            raise ValueError("Missing required 'mac_monitoring' configuration section")
        return config
    
    def get_ami_config(self) -> Dict[str, Any]:
        """Get all AMI-related configuration"""
        config = self.get('ami')
        if config is None:
            raise ValueError("Missing required 'ami' configuration section")
        return config
    
    def get_infrastructure_config(self) -> Dict[str, Any]:
        """Get all infrastructure-related configuration"""
        config = self.get('infrastructure')
        if config is None:
            raise ValueError("Missing required 'infrastructure' configuration section")
        return config
    
    def get_step_function_config(self) -> Dict[str, Any]:
        """Get all Step Function-related configuration"""
        config = self.get('step_function')
        if config is None:
            raise ValueError("Missing required 'step_function' configuration section")
        return config
    
    def get_lambda_config(self) -> Dict[str, Any]:
        """Get all Lambda-related configuration"""
        config = self.get('lambda')
        if config is None:
            raise ValueError("Missing required 'lambda' configuration section")
        return config
    
    def update_config(self, key_path: str, value: Any) -> None:
        """
        Update a configuration value
        
        Args:
            key_path: Dot-separated path to the configuration value
            value: New value to set
        """
        if not isinstance(key_path, str) or not key_path or not key_path.strip():
            raise ValueError("key_path must be a non-empty string")

        keys = key_path.split('.')
        config_ref = self._config
        
        # Navigate to the parent of the target key
        for key in keys[:-1]:
            if key not in config_ref:
                config_ref[key] = {}
            elif not isinstance(config_ref[key], dict):
                current_type = type(config_ref[key]).__name__
                raise TypeError(f"Cannot navigate through non-dictionary value at key '{key}'. Expected dict, got {current_type}. Current value: {config_ref[key]}")
            config_ref = config_ref[key]
        
        # Validate final key is not empty or whitespace-only
        final_key = keys[-1]
        if not final_key or not final_key.strip():
            raise ValueError(f"Final key in path '{key_path}' cannot be empty or whitespace-only")
        
        # Set the final value
        config_ref[final_key] = value
        # Mark cache as dirty instead of immediate invalidation
        self._cache_dirty = True
    
    def save_config(self) -> None:
        """Save the current configuration back to the JSON file"""
        try:
            with open(self.config_path, 'w') as f:
                json.dump(self._config, f, indent=2)
        except (OSError, PermissionError) as e:
            raise OSError(f"Failed to save configuration to {self.config_path}: {e}")
    
    def validate_config(self) -> bool:
        """
        Validate the configuration for required fields and proper types
        
        Returns:
            True if configuration is valid
            
        Raises:
            ValueError: If configuration is invalid
        """
        required_fields = [
            'ec2.ami_id',
            'ec2.instance_type',
            'ami.naming_pattern',
            'infrastructure.vpc.cidr'
        ]
        
        for field in required_fields:
            try:
                value = self.get(field)
                if value is None or value == "":
                    raise ValueError(f"Required configuration field is empty: {field}")
            except KeyError:
                raise ValueError(f"Required configuration field missing: {field}")
        
        # Validate specific field types and values
        instance_type = self.get('ec2.instance_type')
        if not isinstance(instance_type, str):
            raise ValueError(f"EC2 instance type must be a string: {instance_type}")
        
        # This automation only supports Mac2 (Apple Silicon) instances
        if not instance_type.startswith('mac2'):
            if instance_type.startswith('mac1'):
                raise ValueError(f"Mac1 instance type '{instance_type}' is not supported. This automation requires Mac2 (Apple Silicon) instances for DCV compatibility. Supported types: mac2-m1.metal, mac2-m2.metal, mac2-m2pro.metal")
            elif instance_type.startswith('mac'):
                raise ValueError(f"Unsupported Mac instance type '{instance_type}'. Only Mac2 (Apple Silicon) instances are supported: mac2-m1.metal, mac2-m2.metal, mac2-m2pro.metal")
            else:
                raise ValueError(f"Non-Mac instance type '{instance_type}' is not supported. This automation is specifically designed for Mac2 (Apple Silicon) instances: mac2-m1.metal, mac2-m2.metal, mac2-m2pro.metal")
        
        vpc_cidr = self.get('infrastructure.vpc.cidr')
        if not isinstance(vpc_cidr, str) or '/' not in vpc_cidr:
            raise ValueError(f"Invalid VPC CIDR format: {vpc_cidr}")
        
        return True
    
    def get_runtime_environment_vars(self) -> Dict[str, str]:
        """
        Get environment variables for Lambda functions based on configuration
        
        Returns:
            Dictionary of environment variables
        """
        # Cache serialized config to avoid repeated JSON serialization
        if self._cached_config_json is None or self._cache_dirty:
            self._cached_config_json = json.dumps(self._config)
            self._cache_dirty = False
        
        env_vars = {
            'CONFIG_JSON': self._cached_config_json,
            'AMI_NAMING_PATTERN': self.get('ami.naming_pattern'),
            'LOG_LEVEL': self.get('lambda.environment_variables.LOG_LEVEL', 'INFO')
        }
        
        # Add any custom environment variables from config
        custom_env_vars = self.get('lambda.environment_variables', {})
        env_vars.update({k: str(v) for k, v in custom_env_vars.items()})
        
        return env_vars


# Global configuration instance
_config_instance = None

def get_config() -> ConfigLoader:
    """Get the global configuration instance"""
    global _config_instance
    if _config_instance is None:
        _config_instance = ConfigLoader()
    return _config_instance

def load_config_from_env() -> Dict[str, Any]:
    """
    Load configuration from environment variable (for Lambda functions)
    
    Returns:
        Configuration dictionary
    """
    config_json = os.environ.get('CONFIG_JSON')
    if config_json:
        try:
            return json.loads(config_json)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in CONFIG_JSON environment variable: {e}")
    else:
        # Fallback to loading from file
        return get_config()._config