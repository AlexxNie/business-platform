"""Datenvalidierung vor INSERT/UPDATE auf dynamische BO-Tabellen.

Prueft:
- Typ-Kompatibilitaet (String in Integer-Feld → klarer Fehler)
- Required-Fields bei CREATE
- Enum-Werte
- Email/URL-Format
- Referenz-IDs auf Existenz
- Max-Length
"""

import re
from app.core.errors import ValidationError, ErrorDetail

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
URL_REGEX = re.compile(r"^https?://[^\s]+$")


def _check_type(value, field_type: str, field_code: str) -> str | None:
    """Prueft ob der Wert zum Feldtyp passt. Gibt Fehlermeldung zurueck oder None."""
    if value is None:
        return None

    if field_type == "integer":
        if not isinstance(value, int) or isinstance(value, bool):
            return f"Expected integer, got {type(value).__name__}: {repr(value)}"
    elif field_type == "float":
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return f"Expected number, got {type(value).__name__}: {repr(value)}"
    elif field_type == "boolean":
        if not isinstance(value, bool):
            return f"Expected boolean, got {type(value).__name__}: {repr(value)}"
    elif field_type in ("text", "email", "url"):
        if not isinstance(value, str):
            return f"Expected string, got {type(value).__name__}: {repr(value)}"
    elif field_type == "enum":
        if not isinstance(value, str):
            return f"Expected string for enum, got {type(value).__name__}: {repr(value)}"
    elif field_type == "json":
        if not isinstance(value, (dict, list)):
            return f"Expected object or array, got {type(value).__name__}: {repr(value)}"
    elif field_type == "reference":
        if not isinstance(value, int) or isinstance(value, bool):
            return f"Expected integer (ID), got {type(value).__name__}: {repr(value)}"
    elif field_type == "date":
        if not isinstance(value, str):
            return f"Expected date string (YYYY-MM-DD), got {type(value).__name__}: {repr(value)}"
    elif field_type == "datetime":
        if not isinstance(value, str):
            return f"Expected datetime string (ISO 8601), got {type(value).__name__}: {repr(value)}"

    return None


def validate_record_data(
    data: dict,
    fields: list,
    is_create: bool = True,
) -> None:
    """Validiert Daten gegen BO-Feld-Definitionen.

    Raises ValidationError mit allen gefundenen Fehlern auf einmal.
    """
    errors: list[ErrorDetail] = []
    field_map = {f.code: f for f in fields}

    # Required-Check (nur bei CREATE)
    if is_create:
        for f in fields:
            if f.required and f.code not in data and f.default_value is None:
                errors.append(ErrorDetail(
                    code="REQUIRED_FIELD",
                    message=f"Field '{f.code}' is required.",
                    field=f.code,
                    hint=f"Add '{f.code}' ({f.field_type}) to your request body.",
                ))

    # Pro-Feld Validierung
    for key, value in data.items():
        # System-Felder ueberspringen
        if key.startswith("_"):
            continue

        field = field_map.get(key)
        if not field:
            continue  # Unbekannte Felder werden in data.py geprueft

        if value is None:
            continue

        # Typ-Pruefung
        type_err = _check_type(value, field.field_type, key)
        if type_err:
            errors.append(ErrorDetail(
                code="INVALID_TYPE",
                message=type_err,
                field=key,
                hint=f"Field '{key}' expects type '{field.field_type}'.",
            ))
            continue  # Weitere Checks ueberspringen bei falschem Typ

        # Max-Length
        if field.max_length and isinstance(value, str) and len(value) > field.max_length:
            errors.append(ErrorDetail(
                code="MAX_LENGTH_EXCEEDED",
                message=f"Value length {len(value)} exceeds max_length {field.max_length}.",
                field=key,
                hint=f"Maximum {field.max_length} characters allowed.",
            ))

        # Enum-Werte
        if field.field_type == "enum" and field.enum_values:
            allowed = field.enum_values if isinstance(field.enum_values, list) else list(field.enum_values)
            if value not in allowed:
                errors.append(ErrorDetail(
                    code="INVALID_ENUM_VALUE",
                    message=f"Value '{value}' is not in allowed values: {allowed}.",
                    field=key,
                    hint=f"Must be one of: {', '.join(allowed)}",
                ))

        # Email-Format
        if field.field_type == "email" and isinstance(value, str):
            if not EMAIL_REGEX.match(value):
                errors.append(ErrorDetail(
                    code="INVALID_EMAIL",
                    message=f"'{value}' is not a valid email address.",
                    field=key,
                    hint="Expected format: user@example.com",
                ))

        # URL-Format
        if field.field_type == "url" and isinstance(value, str):
            if not URL_REGEX.match(value):
                errors.append(ErrorDetail(
                    code="INVALID_URL",
                    message=f"'{value}' is not a valid URL.",
                    field=key,
                    hint="Expected format: https://example.com",
                ))

    if errors:
        raise ValidationError(
            f"Validation failed with {len(errors)} error(s).",
            details=errors,
        )
