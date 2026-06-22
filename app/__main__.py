"""
__main__.py — `python -m app` entrypoint.
"""

from fasthtml.common import serve

from app.config import PORT
from app.main import app  # noqa: F401  (build the app)

if __name__ == "__main__":
    serve(appname="app.main", app="app", port=PORT)
