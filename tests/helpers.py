from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASES = [f"bill_{number:03}" for number in range(1, 6)]
