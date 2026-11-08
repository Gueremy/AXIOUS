"""ASGI entry point for browser tests against the guarded synthetic SQLite database."""
from pathlib import Path
from sqlalchemy.engine import make_url
from app.core.config import settings

url = make_url(settings.DATABASE_URL)
expected = (Path(__file__).resolve().parents[1] / ".cache" / "browser-test.sqlite").resolve()
if settings.ENVIRONMENT != "test" or url.drivername != "sqlite+aiosqlite" or Path(url.database).resolve() != expected:
    raise RuntimeError("La aplicación de pruebas requiere la base aislada .cache/browser-test.sqlite y ENVIRONMENT=test")

from app.main import app  # noqa: E402
from app.core.limiter import limiter  # noqa: E402

# The production entry point keeps its normal login limit. Browser tests create
# fresh contexts and perform more than five legitimate logins in five minutes.
limiter.enabled = False
