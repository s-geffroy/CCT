"""Erreurs metier, converties en reponses JSON sures par l'API."""
from __future__ import annotations

from typing import Any


class DomainError(Exception):
    status_code = 422

    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


class InvalidInput(DomainError):
    status_code = 422


class TooLarge(DomainError):
    status_code = 413


class NotFound(DomainError):
    status_code = 404
