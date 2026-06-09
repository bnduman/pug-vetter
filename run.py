"""Launch the PuG Vetter web app: python run.py  ->  http://127.0.0.1:8000"""
from app.main import app

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000, debug=False)
