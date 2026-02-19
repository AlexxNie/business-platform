from pydantic import BaseModel, Field, field_validator
from datetime import datetime
import re

CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_]{1,48}$")


class ModuleCreate(BaseModel):
    """Neues Modul erstellen (z.B. CRM, CAFM, HR)."""
    code: str = Field(
        ...,
        description="Eindeutiger Code (lowercase, a-z0-9_, 2-50 Zeichen). Beispiel: 'crm'",
        json_schema_extra={"examples": ["crm"]},
    )
    name: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Anzeigename des Moduls.",
        json_schema_extra={"examples": ["Customer Relationship Management"]},
    )
    description: str | None = Field(
        None,
        max_length=2000,
        description="Optionale Beschreibung.",
    )
    icon: str | None = Field(
        None,
        max_length=50,
        description="Icon-Name (z.B. 'users', 'building').",
    )

    @field_validator("code")
    @classmethod
    def validate_code(cls, v: str) -> str:
        v = v.strip().lower()
        if not CODE_PATTERN.match(v):
            raise ValueError(
                f"Module code must match pattern ^[a-z][a-z0-9_]{{1,48}}$ — "
                f"lowercase, starts with letter, 2-50 chars. Got: '{v}'"
            )
        return v

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "code": "crm",
                    "name": "Customer Relationship Management",
                    "description": "Kunden, Deals und Pipeline verwalten",
                    "icon": "users",
                }
            ]
        }
    }


class ModuleUpdate(BaseModel):
    """Modul aktualisieren (nur gesetzte Felder werden geaendert)."""
    name: str | None = Field(None, min_length=1, max_length=200, description="Neuer Anzeigename.")
    description: str | None = Field(None, max_length=2000, description="Neue Beschreibung.")
    icon: str | None = Field(None, max_length=50, description="Neues Icon.")
    is_active: bool | None = Field(None, description="Modul aktivieren/deaktivieren.")


class ModuleResponse(BaseModel):
    """Modul-Response mit allen Feldern."""
    id: int
    code: str
    name: str
    description: str | None
    icon: str | None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}
