"""Explicit GPU benchmark entry point; results are measured, not inferred."""
import runpy
from pathlib import Path
runpy.run_path(str(Path(__file__).resolve().parents[1]/'scripts/benchmark.py'),run_name='__main__')
