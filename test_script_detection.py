#!/usr/bin/env python3
import os
import sys
sys.path.insert(0, '/app/src')

from pathlib import Path
from desto.app.sessions import TmuxManager
from desto.app.ui import UserInterfaceManager
from desto.app.config import config as ui_settings

# Create a mock UI object
class MockUI:
    def column(self):
        return self
    def style(self, style):
        return self
    def notification(self, msg, type=None):
        print(f"NOTIFICATION ({type}): {msg}")

# Create a mock logger
class MockLogger:
    def info(self, msg):
        print(f"INFO: {msg}")
    def warning(self, msg):
        print(f"WARNING: {msg}")
    def error(self, msg):
        print(f"ERROR: {msg}")

print("=== Testing TmuxManager Initialization ===")
mock_ui = MockUI()
mock_logger = MockLogger()

print(f"Environment variables:")
print(f"  DESTO_SCRIPTS_DIR: {os.environ.get('DESTO_SCRIPTS_DIR')}")
print(f"  DESTO_LOGS_DIR: {os.environ.get('DESTO_LOGS_DIR')}")

print("\nCreating TmuxManager...")
tm = TmuxManager(mock_ui, mock_logger)
print(f"TmuxManager.SCRIPTS_DIR: {tm.SCRIPTS_DIR}")
print(f"TmuxManager.LOG_DIR: {tm.LOG_DIR}")
print(f"Scripts directory exists: {tm.SCRIPTS_DIR.exists()}")
print(f"Scripts directory is_dir: {tm.SCRIPTS_DIR.is_dir()}")

if tm.SCRIPTS_DIR.exists():
    print(f"Scripts directory contents: {list(tm.SCRIPTS_DIR.iterdir())}")

print("\nCreating UserInterfaceManager...")
um = UserInterfaceManager(mock_ui, ui_settings, tm)
print(f"Getting script files...")
script_files = um.get_script_files()
print(f"Script files found: {script_files}")

print("\nTesting script path resolution...")
if script_files:
    for script_file in script_files:
        script_path = tm.SCRIPTS_DIR / script_file
        print(f"  {script_file}: {script_path}")
        print(f"    exists: {script_path.exists()}")
        print(f"    is_file: {script_path.is_file()}")
        print(f"    readable: {os.access(script_path, os.R_OK)}")
