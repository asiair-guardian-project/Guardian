from modules.asiair_monitor import asiair_available


host = "asiair.local"

print(f"Testing ASIAIR at {host}")

if asiair_available(host):
    print("ASIAIR available")
else:
    print("ASIAIR unavailable")