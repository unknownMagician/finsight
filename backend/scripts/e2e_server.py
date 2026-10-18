"""Start the API for end-to-end tests: fresh SQLite database, migrations, demo providers.

Usage: python scripts/e2e_server.py [port]   (run from backend/)
"""

import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
DB = BACKEND / "e2e.db"


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    DB.unlink(missing_ok=True)
    os.environ.update(
        FINSIGHT_ENVIRONMENT="test",
        FINSIGHT_DATABASE_URL=f"sqlite:///{DB.as_posix()}",
        FINSIGHT_MARKET_DATA_PROVIDER="demo",
        FINSIGHT_FUNDAMENTALS_PROVIDER="demo",
        FINSIGHT_LOG_JSON="false",
        FINSIGHT_LOG_LEVEL="WARNING",
    )
    os.environ.pop("FINSIGHT_ANTHROPIC_API_KEY", None)  # E2E never calls a paid API
    sys.path.insert(0, str(BACKEND))

    from alembic import command
    from alembic.config import Config

    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    config.set_main_option("sqlalchemy.url", os.environ["FINSIGHT_DATABASE_URL"])
    command.upgrade(config, "head")

    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
