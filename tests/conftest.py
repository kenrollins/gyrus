"""Settings need a DSN at import; tests never touch the database."""
import os

os.environ.setdefault("GYRUS_PG_DSN", "postgresql://test@localhost/test")
