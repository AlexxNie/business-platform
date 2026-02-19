from pydantic import BaseModel, Field, field_validator, model_validator
from datetime import datetime
import re

CODE_PATTERN = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]{1,98}$")
FIELD_CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_]{1,98}$")

VALID_FIELD_TYPES = [
    "text", "integer", "float", "boolean",
    "date", "datetime", "email", "url",
    "enum", "json", "reference",
]

# Reservierte Feldnamen (System-Spalten)
RESERVED_FIELD_CODES = {"id", "_state", "_created_at", "_updated_at", "_created_by", "_notes"}


class FieldCreate(BaseModel):
    """Feld-Definition fuer ein Business Object."""
    code: str = Field(
        ...,
        description="Technischer Feldname (lowercase, a-z0-9_, 2-100 Zeichen). Beispiel: 'company_name'",
        json_schema_extra={"examples": ["company_name"]},
    )
    name: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Anzeigename des Feldes.",
        json_schema_extra={"examples": ["Firmenname"]},
    )
    field_type: str = Field(
        ...,
        description=f"Feldtyp. Erlaubt: {', '.join(VALID_FIELD_TYPES)}",
        json_schema_extra={"examples": ["text"]},
    )
    description: str | None = Field(
        None, max_length=2000,
        description="Optionale Feldbeschreibung.",
    )
    required: bool = Field(
        False,
        description="Pflichtfeld? Wenn True, darf der Wert nicht NULL sein.",
    )
    unique: bool = Field(
        False,
        description="Eindeutig? Wenn True, wird ein UNIQUE-Constraint angelegt.",
    )
    indexed: bool = Field(
        False,
        description="Index anlegen? Empfohlen fuer Referenz- und haeufig gefilterte Felder.",
    )
    max_length: int | None = Field(
        None, gt=0, le=10000,
        description="Maximale Zeichenlaenge (nur fuer text-Felder).",
    )
    default_value: str | None = Field(
        None, max_length=1000,
        description="Default-Wert als String (z.B. '0', 'active', 'true').",
    )
    enum_values: list[str] | None = Field(
        None,
        description="Erlaubte Werte (nur fuer field_type='enum'). Beispiel: ['active', 'inactive']",
        json_schema_extra={"examples": [["active", "inactive"]]},
    )
    reference_bo_code: str | None = Field(
        None,
        description="Code des referenzierten BOs (nur fuer field_type='reference'). Beispiel: 'Company'",
    )
    is_searchable: bool = Field(
        False,
        description="Feld in Volltextsuche einbeziehen?",
    )
    sort_order: int = Field(
        0,
        description="Reihenfolge in der Anzeige (aufsteigend).",
    )

    @field_validator("code")
    @classmethod
    def validate_code(cls, v: str) -> str:
        v = v.strip()
        if v.lower() in RESERVED_FIELD_CODES:
            raise ValueError(
                f"Field code '{v}' is reserved (system columns: {sorted(RESERVED_FIELD_CODES)}). "
                f"Choose a different name."
            )
        if not FIELD_CODE_PATTERN.match(v):
            raise ValueError(
                f"Field code must match ^[a-z][a-z0-9_]{{1,98}}$ — "
                f"lowercase, starts with letter, 2-100 chars. Got: '{v}'"
            )
        return v

    @field_validator("field_type")
    @classmethod
    def validate_field_type(cls, v: str) -> str:
        if v not in VALID_FIELD_TYPES:
            raise ValueError(
                f"field_type must be one of {VALID_FIELD_TYPES}. Got: '{v}'"
            )
        return v

    @model_validator(mode="after")
    def cross_field_validation(self):
        # enum braucht enum_values
        if self.field_type == "enum" and not self.enum_values:
            raise ValueError(
                "field_type 'enum' requires 'enum_values' (list of allowed strings). "
                "Example: [\"active\", \"inactive\"]"
            )
        # reference braucht reference_bo_code
        if self.field_type == "reference" and not self.reference_bo_code:
            raise ValueError(
                "field_type 'reference' requires 'reference_bo_code' (code of the referenced BO). "
                "Example: \"Company\""
            )
        # max_length nur fuer text sinnvoll
        if self.max_length and self.field_type != "text":
            raise ValueError(
                f"max_length is only valid for field_type 'text', not '{self.field_type}'."
            )
        # enum_values nur fuer enum sinnvoll
        if self.enum_values and self.field_type != "enum":
            raise ValueError(
                f"enum_values is only valid for field_type 'enum', not '{self.field_type}'."
            )
        return self


class FieldResponse(BaseModel):
    """Feld-Response mit allen Attributen."""
    id: int
    code: str
    name: str
    field_type: str
    description: str | None
    required: bool
    unique: bool
    indexed: bool
    max_length: int | None
    default_value: str | None
    enum_values: list[str] | dict | None
    reference_bo_code: str | None
    is_searchable: bool
    sort_order: int

    model_config = {"from_attributes": True}


class WorkflowStateCreate(BaseModel):
    """Ein Workflow-State (z.B. 'lead', 'qualified', 'won')."""
    code: str = Field(..., min_length=1, max_length=100, description="State-Code.")
    name: str = Field(..., min_length=1, max_length=200, description="Anzeigename.")
    color: str | None = Field(None, max_length=20, description="Hex-Farbe fuer UI (z.B. '#3b82f6').")
    is_final: bool = Field(False, description="End-State? (z.B. 'won', 'lost')")
    sort_order: int = Field(0, description="Reihenfolge in der Anzeige.")


class WorkflowTransitionCreate(BaseModel):
    """Eine Workflow-Transition (z.B. lead → qualified via 'qualify')."""
    code: str = Field(..., min_length=1, max_length=100, description="Transition-Code.")
    name: str = Field(..., min_length=1, max_length=200, description="Anzeigename.")
    from_state: str = Field(..., description="Ausgangs-State.")
    to_state: str = Field(..., description="Ziel-State.")
    conditions: dict | None = Field(None, description="Optionale Bedingungen (JSONB).")
    webhook_url: str | None = Field(None, description="Optionaler Webhook bei Transition.")


class WorkflowCreate(BaseModel):
    """Workflow-Definition mit States und Transitions."""
    initial_state: str = Field(..., description="Anfangs-State fuer neue Datensaetze.")
    states: list[WorkflowStateCreate] = Field(
        ..., min_length=1,
        description="Liste aller moeglichen States.",
    )
    transitions: list[WorkflowTransitionCreate] = Field(
        default_factory=list,
        description="Liste der erlaubten Transitions.",
    )

    @model_validator(mode="after")
    def validate_workflow_consistency(self):
        state_codes = {s.code for s in self.states}
        if self.initial_state not in state_codes:
            raise ValueError(
                f"initial_state '{self.initial_state}' is not in states: {sorted(state_codes)}"
            )
        for t in self.transitions:
            if t.from_state not in state_codes:
                raise ValueError(
                    f"Transition '{t.code}': from_state '{t.from_state}' is not in states: {sorted(state_codes)}"
                )
            if t.to_state not in state_codes:
                raise ValueError(
                    f"Transition '{t.code}': to_state '{t.to_state}' is not in states: {sorted(state_codes)}"
                )
        return self


class BODefinitionCreate(BaseModel):
    """Business Object Definition erstellen.

    Erstellt eine BO-Definition und die zugehoerige PostgreSQL-Tabelle.
    """
    code: str = Field(
        ...,
        description=(
            "Eindeutiger BO-Code (Buchstaben, Zahlen, Underscore, 2-100 Zeichen, "
            "beginnt mit Buchstabe). Beispiel: 'Company'"
        ),
        json_schema_extra={"examples": ["Company"]},
    )
    name: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Anzeigename. Beispiel: 'Unternehmen'",
        json_schema_extra={"examples": ["Unternehmen"]},
    )
    description: str | None = Field(
        None,
        max_length=2000,
        description="Optionale Beschreibung.",
    )
    module_code: str | None = Field(
        None,
        description="Code des Moduls, dem dieses BO zugeordnet wird.",
        json_schema_extra={"examples": ["crm"]},
    )
    icon: str | None = Field(
        None,
        max_length=50,
        description="Icon-Name.",
    )
    parent_bo_code: str | None = Field(
        None,
        description="Code des Eltern-BOs (fuer Hierarchie).",
    )
    display_field: str | None = Field(
        None,
        description="Welches Feld als Label/Titel angezeigt wird.",
    )
    fields: list[FieldCreate] = Field(
        default_factory=list,
        description="Liste der Feld-Definitionen.",
    )
    workflow: WorkflowCreate | None = Field(
        None,
        description="Optionale Workflow-Definition mit States und Transitions.",
    )

    @field_validator("code")
    @classmethod
    def validate_code(cls, v: str) -> str:
        v = v.strip()
        if not CODE_PATTERN.match(v):
            raise ValueError(
                f"BO code must match ^[a-zA-Z][a-zA-Z0-9_]{{1,98}}$ — "
                f"starts with letter, 2-100 chars. Got: '{v}'"
            )
        return v

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "code": "Company",
                    "name": "Unternehmen",
                    "module_code": "crm",
                    "display_field": "name",
                    "fields": [
                        {
                            "code": "name",
                            "name": "Firmenname",
                            "field_type": "text",
                            "required": True,
                            "is_searchable": True,
                        },
                        {
                            "code": "industry",
                            "name": "Branche",
                            "field_type": "enum",
                            "enum_values": ["tech", "manufacturing", "services"],
                        },
                    ],
                }
            ]
        }
    }


class BODefinitionResponse(BaseModel):
    """BO-Definition Response mit Feldern."""
    id: int
    code: str
    name: str
    description: str | None
    table_name: str
    is_active: bool
    table_created: bool
    display_field: str | None
    fields: list[FieldResponse]
    created_at: datetime

    model_config = {"from_attributes": True}


class BODefinitionList(BaseModel):
    """BO-Definition in Listenansicht (kompakt)."""
    id: int
    code: str
    name: str
    module_code: str | None = None
    table_name: str
    is_active: bool
    table_created: bool
    field_count: int = 0

    model_config = {"from_attributes": True}


class SchemaProposal(BaseModel):
    """AI-generierter Vorschlag fuer ein neues BO oder Feld-Erweiterung."""
    action: str  # "create_bo", "add_field", "add_workflow"
    description: str
    definition: BODefinitionCreate | FieldCreate | WorkflowCreate
