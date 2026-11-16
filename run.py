"""Triathlon Performance & Health Platform Runner.
Launches the FastAPI server accessible from PC, Mobile Wi-Fi, and 4G/5G remotely via Cloudflare Tunnel.
"""

import atexit
import os
import re
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

# Ensure UTF-8 output on Windows consoles
if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

APP_DIR = Path.home() / ".tricoach"
APP_DIR.mkdir(parents=True, exist_ok=True)
TUNNEL_FILE = APP_DIR / "public_tunnel_url.txt"
CLOUDFLARED_EXE = APP_DIR / "cloudflared.exe"

tunnel_process = None


def cleanup_tunnel():
    global tunnel_process
    if tunnel_process:
        try:
            tunnel_process.terminate()
            tunnel_process.wait(timeout=2)
        except Exception:
            pass
    if TUNNEL_FILE.exists():
        try:
            TUNNEL_FILE.unlink()
        except Exception:
            pass


atexit.register(cleanup_tunnel)


def start_tunnel_in_background():
    """Starts cloudflared quick tunnel to expose port 8000 securely over HTTPS worldwide."""
    global tunnel_process
    if not CLOUDFLARED_EXE.exists():
        return

    # Clear old url file
    if TUNNEL_FILE.exists():
        try:
            TUNNEL_FILE.unlink()
        except Exception:
            pass

    cmd = [str(CLOUDFLARED_EXE), "tunnel", "--url", "http://127.0.0.1:8000"]
    try:
        tunnel_process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )

        def monitor_tunnel():
            for line in iter(tunnel_process.stdout.readline, ""):
                m = re.search(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com", line)
                if m:
                    public_url = m.group(0)
                    with open(TUNNEL_FILE, "w", encoding="utf-8") as f:
                        f.write(public_url)
                    print("\n" + "=" * 68)
                    print(f"  [>] ENLACE PUBLICO PARA TU MOVIL (4G/5G / Sin Wi-Fi):")
                    print(f"      {public_url}")
                    print("=" * 68 + "\n")
                    break

        threading.Thread(target=monitor_tunnel, daemon=True).start()
    except Exception as e:
        print(f"  [-] Aviso: No se pudo iniciar el túnel público: {e}")


def get_local_ip() -> str:
    """Detect the local Wi-Fi / LAN IP address."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "192.168.1.135"


def open_browser(url: str):
    time.sleep(1.2)
    try:
        webbrowser.open(url)
    except Exception:
        pass


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    is_cloud = bool(os.environ.get("RENDER") or os.environ.get("RAILWAY_STATIC_URL") or os.environ.get("DYNO") or os.environ.get("FLY_ALLOC_ID") or os.environ.get("KOYEB_APP_NAME"))

    if not is_cloud:
        local_ip = get_local_ip()

        print("=" * 68)
        print("  [+] TRIATHLON PERFORMANCE & HEALTH PLATFORM")
        print("      Garmin Connect + Intervals.icu + Coach IA Especialista")
        print("=" * 68)
        print(f"  * Acceso desde tu Ordenador:  http://localhost:{port}")
        print(f"  * Acceso en misma red Wi-Fi:  http://{local_ip}:{port}")
        print("  * Generando enlace 4G/5G para tu móvil...")
        print("=" * 68)

        # Launch tunnel in background
        start_tunnel_in_background()

        # Launch browser automatically on the computer
        threading.Thread(target=open_browser, args=(f"http://localhost:{port}",), daemon=True).start()

    import uvicorn
    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=port,
        reload=False,
        log_level="info"
    )
