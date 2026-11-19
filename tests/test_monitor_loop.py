from modules.guardian import Guardian
from modules.monitor_loop import MonitorLoop


guardian = Guardian()

loop = MonitorLoop(guardian)

loop.run(cycles=5)