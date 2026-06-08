import sys
from importlib.resources import files

try:
    path = files("cloud_telemetry_backend").joinpath("static", "logo.png")
    print("Resolved path:", path)
    print("Exists:", path.exists())
    if path.exists():
        data = path.read_bytes()
        print("Bytes read:", len(data))
except Exception as e:
    print("Error:", e)
sys.exit(0)
