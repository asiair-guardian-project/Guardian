import yaml
from pathlib import Path


CONFIG_FILE = Path("config/config.yaml")
EXAMPLE_CONFIG_FILE = Path("config/config.example.yaml")


def load_config():
    """Load and return the observatory configuration.

    Uses config/config.yaml. If this copy has none yet (a fresh download),
    the example configuration is used so nothing starts from an empty file.
    """

    path = CONFIG_FILE if CONFIG_FILE.exists() else EXAMPLE_CONFIG_FILE
    with open(path, "r", encoding="utf-8") as file:
        return yaml.safe_load(file)
