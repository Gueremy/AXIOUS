"""Tipos portables del dominio v2."""
from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB


JSONDocument = JSON().with_variant(JSONB(), "postgresql")
