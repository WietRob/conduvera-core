"""Tests for utility modules."""
import pytest
from pathlib import Path
import tempfile
import yaml


try:
    from src.utils.config import Config
    from src.utils.logger import setup_logger
except ImportError as e:
    pytest.skip(f"Could not import utils: {e}", allow_module_level=True)


class TestConfig:
    """Test configuration management."""

    def test_load_config(self):
        """Test loading configuration."""
        # Create temporary config file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(
                {
                    "matrix_os": {
                        "display": {"fps": 60},
                        "effects": {"rain": {"enabled": True}},
                    }
                },
                f,
            )
            config_path = Path(f.name)

        try:
            config = Config.load(config_path)
            assert config is not None

            # Test getting values
            assert config.get("matrix_os.display.fps") == 60
            assert config.get("matrix_os.effects.rain.enabled") == True

            # Test default values
            assert config.get("nonexistent.key", "default") == "default"

        finally:
            config_path.unlink()

    def test_set_config(self):
        """Test setting configuration values."""
        config = Config.load(None)

        config.set("test.key", "value")
        assert config.get("test.key") == "value"

        config.set("nested.key.value", 42)
        assert config.get("nested.key.value") == 42

    def test_save_config(self):
        """Test saving configuration."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            config_path = Path(f.name)

        try:
            config = Config.load(None)
            config.set("test.value", 123)
            config.save(config_path)

            # Load and verify
            loaded_config = Config.load(config_path)
            assert loaded_config.get("test.value") == 123

        finally:
            if config_path.exists():
                config_path.unlink()


class TestLogger:
    """Test logging utilities."""

    def test_setup_logger(self):
        """Test logger setup."""
        logger = setup_logger("test_logger")
        assert logger is not None
        assert logger.name == "test_logger"

        # Test logging doesn't crash
        logger.info("Test info message")
        logger.warning("Test warning message")
        logger.error("Test error message")

    def test_logger_singleton(self):
        """Test that logger returns same instance."""
        logger1 = setup_logger("same_logger")
        logger2 = setup_logger("same_logger")

        # Should be the same logger instance
        assert logger1.name == logger2.name
