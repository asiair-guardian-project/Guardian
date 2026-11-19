from modules.config_loader import load_config
from modules.network_monitor import internet_available


config = load_config()

test_url = config["network"]["internet_test_url"]
timeout = config["network"]["timeout_seconds"]

print(f"Testing {test_url}")

if internet_available(test_url, timeout):
    print("Internet available")
else:
    print("Internet unavailable")