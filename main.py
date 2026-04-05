"""Taipy CLI entrypoint.

Run with:
  taipy run main.py
"""

# Re-export the public GUI namespace so Taipy can resolve callbacks against the
# entry module when launched through `taipy run main.py`.
from app import *  # noqa: F401,F403


if __name__ == "__main__":
    run_app()
