#!/usr/bin/env python3

"""
Example Python script for desto Docker demo
"""

import os
import sys
import time
from datetime import datetime


def main():
    print("=== Docker Python Demo Script ===")
    print(f"Starting at: {datetime.now()}")
    print(f"Python version: {sys.version}")
    print(f"Container hostname: {os.uname().nodename}")
    print(f"Current directory: {os.getcwd()}")

    print("\nDesto environment variables:")
    for key, value in os.environ.items():
        if key.startswith('DESTO'):
            print(f"  {key}: {value}")

    print("\nRunning Python demo tasks...")
    tasks = [
        "Initializing modules",
        "Loading configuration",
        "Processing data batch 1",
        "Processing data batch 2",
        "Generating reports",
        "Cleanup and finalization"
    ]

    for i, task in enumerate(tasks, 1):
        print(f"Task {i}/{len(tasks)}: {task}")
        time.sleep(1.5)

    print(f"\nDemo completed successfully at: {datetime.now()}")

if __name__ == "__main__":
    main()
