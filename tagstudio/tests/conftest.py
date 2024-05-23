import sys
from pathlib import Path

ROOT_TESTS = Path(__file__).parents[1]
sys.path.insert(0, str(Path(__file__).parents[1]))
