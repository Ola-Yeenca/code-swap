from app.models import Base

# Import models so Alembic can discover metadata.
from app.models import entities  # noqa: F401

__all__ = ["Base"]
