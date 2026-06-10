"""Production launcher (waitress) — use this instead of run.py when hosting
the app anywhere public; Flask's built-in dev server is single-purpose and
not meant for real traffic.

    python serve.py            -> http://0.0.0.0:8000
"""
from waitress import serve

from app.main import app

if __name__ == "__main__":
    serve(app, host="0.0.0.0", port=8000)
