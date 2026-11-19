from modules.ups_monitor import read_ups_status


status = read_ups_status()

print(f"UPS present: {status['ups_present']}")
print(f"Power source: {status['power_source']}")
print(f"Battery: {status['battery_percent']}%")
print(f"State: {status['state']}")
print(f"Runtime: {status['runtime']}")