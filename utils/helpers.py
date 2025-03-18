import json
from typing import Any, Callable, Dict, Optional

def load_json(file_path: str) -> dict:
    """Load and parse a JSON file"""
    try:
        with open(file_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        raise ValueError(f"Error loading JSON file {file_path}: {str(e)}")

def validate_config(config: Any, validator: Callable[[Any], None], name: str) -> None:
    """Generic configuration validation helper
    
    Args:
        config: Configuration object to validate
        validator: Validation function to apply
        name: Name of the configuration (for error messages)
    """
    try:
        validator(config)
    except Exception as e:
        raise ValueError(f"Invalid {name} configuration: {str(e)}")

def validate_all_numeric_positive(
    config_dict: Dict[str, float],
    allow_zero: bool = False,
    exceptions: Optional[list] = None
) -> None:
    """Validate that all numeric values in a dictionary are positive
    
    Args:
        config_dict: Dictionary of configuration values
        allow_zero: Whether to allow zero values
        exceptions: List of keys to skip validation for
    """
    exceptions = exceptions or []
    for key, value in config_dict.items():
        if key in exceptions:
            continue
        if not isinstance(value, (int, float)):
            raise ValueError(f"{key} must be a number")
        if allow_zero:
            if value < 0:
                raise ValueError(f"{key} must be non-negative")
        else:
            if value <= 0:
                raise ValueError(f"{key} must be positive")
