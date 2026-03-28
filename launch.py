import os
import sys
import socket
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from App.app import app, AUTO_REFRESH_ON_STARTUP, APP_DEBUG, APP_PORT
from Database.Wet.Wet_Pipeline import run_wet_pipeline

if __name__ == '__main__':
    if AUTO_REFRESH_ON_STARTUP:
        run_wet_pipeline()

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as _s:
        if _s.connect_ex(('127.0.0.1', APP_PORT)) == 0:
            print(f"\n*** ERROR: Port {APP_PORT} is already in use! ***")
            print("Please stop the old server first, then restart.")
            sys.exit(1)

    app.run(debug=APP_DEBUG, use_reloader=APP_DEBUG, port=APP_PORT)
