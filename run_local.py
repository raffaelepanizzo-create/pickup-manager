"""
Entry point per deploy LOCALE (chiavetta USB / LAN).

- Imposta DB_PATH e UPLOAD_FOLDER accanto all'eseguibile (persistenza su USB)
- Avvia waitress su 0.0.0.0:5000 (accessibile da tutta la LAN)
- Stampa gli URL di accesso e apre il browser locale

NON usato da Render (che continua a eseguire app.py con gunicorn).
"""
import os
import sys
import socket
import threading
import webbrowser
import time


def get_base_dir():
    """Cartella dove si trova l'eseguibile (o lo script in dev)."""
    if getattr(sys, "frozen", False):
        # PyInstaller onefile: sys.executable e' il .exe sulla chiavetta
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def get_lan_ip():
    """Ritorna l'IP LAN del PC (per accesso da altri dispositivi)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


BASE_DIR = get_base_dir()

# Percorsi persistenti sulla chiavetta (accanto al .exe)
DB_FILE = os.path.join(BASE_DIR, "pickup.db")
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")

os.makedirs(UPLOAD_DIR, exist_ok=True)

# Comunica ad app.py i percorsi prima dell'import
os.environ["PICKUP_DB_PATH"] = DB_FILE
os.environ["PICKUP_UPLOAD_FOLDER"] = UPLOAD_DIR
os.environ.setdefault("SECRET_KEY", "pickup_local_secret_change_me")

# Ora importa l'app Flask
from app import app, init_db

# Inizializza il DB se non esiste
init_db()

PORT = 5000
LAN_IP = get_lan_ip()


def open_browser():
    time.sleep(1.5)
    webbrowser.open(f"http://127.0.0.1:{PORT}")


if __name__ == "__main__":
    print("=" * 60)
    print("  PickUp Manager - Server Locale")
    print("=" * 60)
    print(f"  Database:     {DB_FILE}")
    print(f"  Uploads:      {UPLOAD_DIR}")
    print()
    print("  Accesso dal PC locale:")
    print(f"    http://127.0.0.1:{PORT}")
    print("  Accesso dagli altri PC in LAN:")
    print(f"    http://{LAN_IP}:{PORT}")
    print()
    print("  Credenziali default: admin / changeme")
    print("  (imposta APP_USERNAME e APP_PASSWORD come variabili")
    print("   d'ambiente per cambiarle)")
    print()
    print("  Per fermare il server: chiudi questa finestra")
    print("  oppure premi CTRL+C")
    print("=" * 60)

    threading.Thread(target=open_browser, daemon=True).start()

    try:
        from waitress import serve
        serve(app, host="0.0.0.0", port=PORT, threads=8)
    except ImportError:
        # Fallback al dev server Flask se waitress non e' disponibile
        app.run(host="0.0.0.0", port=PORT, debug=False)
