"""Strukturierte Fehler-Responses fuer maschinenlesbare API-Fehler.

Jeder Fehler hat:
- error: Fehler-Kategorie (conflict, validation, not_found, internal)
- message: Menschenlesbare Zusammenfassung
- details: Liste von ErrorDetail mit code, message, field, hint
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict


@dataclass
class ErrorDetail:
    """Ein einzelnes Fehlerproblem."""
    code: str
    message: str
    field: str | None = None
    hint: str | None = None


@dataclass
class ErrorResponse:
    """Maschinenlesbare Fehler-Response."""
    error: str
    message: str
    details: list[ErrorDetail] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "error": self.error,
            "message": self.message,
            "details": [asdict(d) for d in self.details],
        }


class PlatformError(Exception):
    """Basis-Exception fuer alle Plattform-Fehler."""
    status_code: int = 500
    error_type: str = "internal"

    def __init__(self, message: str, details: list[ErrorDetail] | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or []

    def to_response(self) -> ErrorResponse:
        return ErrorResponse(
            error=self.error_type,
            message=self.message,
            details=self.details,
        )


class ConflictError(PlatformError):
    """409 - Ressource existiert bereits."""
    status_code = 409
    error_type = "conflict"


class ValidationError(PlatformError):
    """422 - Eingabe-Validierungsfehler."""
    status_code = 422
    error_type = "validation"


class NotFoundError(PlatformError):
    """404 - Ressource nicht gefunden."""
    status_code = 404
    error_type = "not_found"
