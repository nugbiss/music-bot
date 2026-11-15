"""Serveur HTTP minimal pour les plateformes qui exigent un port ouvert (Render)."""

import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *args):
        pass


def start_if_needed():
    """Ouvre un port HTTP si la variable PORT existe (Render la fournit).

    Entrée : aucune (lit PORT dans l'environnement).
    Sortie : aucune ; serveur en thread daemon, il meurt avec le process.
    """
    port = os.getenv("PORT")
    if not port:
        return
    server = HTTPServer(("0.0.0.0", int(port)), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"[bot] port HTTP {port} ouvert (health check)")
