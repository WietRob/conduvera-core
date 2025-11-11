"""Configuration management for Matrix OS."""
import yaml
from pathlib import Path
from typing import Any, Optional
from dataclasses import dataclass


@dataclass
class Config:
    """Configuration manager for Matrix OS."""

    _data: dict
    _file_path: Optional[Path] = None

    @classmethod
    def load(cls, config_path: Optional[Path] = None) -> "Config":
        """Load configuration from YAML file."""
        if config_path is None:
            # Try to find config in standard locations
            search_paths = [
                Path.home() / ".config" / "matrix-os" / "config.yaml",
                Path(__file__).parent.parent.parent / "config" / "default.yaml",
            ]
            for path in search_paths:
                if path.exists():
                    config_path = path
                    break

        if config_path and config_path.exists():
            with open(config_path) as f:
                data = yaml.safe_load(f) or {}
        else:
            data = {}

        return cls(_data=data, _file_path=config_path)

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get configuration value using dot notation.

        Example:
            config.get("matrix_os.effects.rain.enabled", True)
        """
        keys = key.split(".")
        value = self._data
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
                if value is None:
                    return default
            else:
                return default
        return value

    def set(self, key: str, value: Any) -> None:
        """Set configuration value using dot notation."""
        keys = key.split(".")
        data = self._data
        for k in keys[:-1]:
            if k not in data:
                data[k] = {}
            data = data[k]
        data[keys[-1]] = value

    def save(self, path: Optional[Path] = None) -> None:
        """Save configuration to YAML file."""
        save_path = path or self._file_path
        if save_path:
            with open(save_path, "w") as f:
                yaml.dump(self._data, f, default_flow_style=False)


# Global config instance
_config: Optional[Config] = None


def get_config() -> Config:
    """Get global configuration instance."""
    global _config
    if _config is None:
        _config = Config.load()
    return _config
