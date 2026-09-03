"""Compatibility entry point: local and API builds share one implementation."""
import runpy
from pathlib import Path

if __name__ == "__main__":
    runpy.run_path(str(Path(__file__).with_name("find_pages_v11_server.py")), run_name="__main__")
