from modules.wave_network import ensure_wave_connection


print("Testing Wave network recovery")
print()

result = ensure_wave_connection()

print(f"Result: {result}")