"""Redirect only configuration storage for real-launcher subprocess tests."""
import os
from pathlib import Path
from iris import local_config

local_config.config_path = lambda: Path(os.environ["IRIS_TEST_CONFIG_PATH"])
