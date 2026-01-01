import sys
import os
sys.path.append(os.path.join(os.getcwd(), "src"))
from src.report_generator import generate_prompt_parts

instructions, logs = generate_prompt_parts("2025-12-31")
print("--- INSTRUCTIONS ---")
print(instructions[:200])
print("\n--- LOGS & STATS ---")
print(logs[-500:]) # Show the end where stats should be
