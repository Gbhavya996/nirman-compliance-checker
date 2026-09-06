"""
app.py
──────
Flask application factory for the Nirman Legal Metrology
Compliance Verification System (SIH 2026 – Problem ID: 26034).
"""

import logging
import os
import sys

from flask import Flask
from flask_cors import CORS

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s – %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


def create_app() -> Flask:
    app = Flask(__name__)

    # ── CORS ──────────────────────────────────────────────────────────────────
    # Allow all origins in development; restrict in production.
    CORS(
        app,
        resources={r"/api/*": {"origins": "*"}},
        supports_credentials=False,
    )

    # ── Register blueprints ───────────────────────────────────────────────────
    # Add the routes directory to the Python path so blueprint imports work.
    routes_dir = os.path.join(os.path.dirname(__file__), "routes")
    services_dir = os.path.join(os.path.dirname(__file__), "services")
    for d in (routes_dir, services_dir):
        if d not in sys.path:
            sys.path.insert(0, d)

    # Also add backend root for `from services.xxx import` style imports
    backend_dir = os.path.dirname(os.path.abspath(__file__))
    if backend_dir not in sys.path:
        sys.path.insert(0, backend_dir)

    from routes.inspections import inspections_bp
    app.register_blueprint(inspections_bp)

    # ── Root route ────────────────────────────────────────────────────────────
    @app.route("/")
    def index():
        return {
            "name": "Nirman Legal Metrology Compliance API",
            "version": "1.0.0",
            "problem_id": "SIH-2026-26034",
            "endpoints": {
                "analyze": "POST /api/inspections/analyze",
                "health": "GET /api/inspections/health",
            },
        }

    logger.info("Nirman API initialised. Blueprints: inspections")
    return app


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "true").lower() == "true"
    app = create_app()
    logger.info("Starting Nirman API on http://127.0.0.1:%d (debug=%s)", port, debug)
    app.run(host="0.0.0.0", port=port, debug=debug)
