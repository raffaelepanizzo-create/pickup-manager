"""Download vendor assets (Bootstrap, Chart.js) in static/vendor/.

Run from build_windows.bat before PyInstaller so assets end up in the .exe
and the app works also offline (USB, isolated LAN).
Idempotent.
"""
import os
import sys
import urllib.request

ASSETS = [
    ("bootstrap.min.css", "https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css"),
    ("bootstrap.bundle.min.js", "https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"),
    ("chart.umd.min.js", "https://cdn.jsdelivr.net/npm/chart.js@4.5.1/dist/chart.umd.min.js"),
]


def main():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    vendor = os.path.join(base, "static", "vendor")
    os.makedirs(vendor, exist_ok=True)
    for name, url in ASSETS:
        dest = os.path.join(vendor, name)
        if os.path.exists(dest) and os.path.getsize(dest) > 0:
            print("[skip] " + name)
            continue
        print("[get ] " + name)
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                data = r.read()
            with open(dest, "wb") as f:
                f.write(data)
            print("[ok  ] " + name + " (" + str(len(data)) + " bytes)")
        except Exception as exc:
            print("[FAIL] " + name + ": " + str(exc))
            sys.exit(1)


if __name__ == "__main__":
    main()
