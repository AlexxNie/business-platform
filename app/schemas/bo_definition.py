from pydantic import BaseModel, field_validator
from datetime import datetime


class FieldCreate(BaseModel):
    code: str
    name: str
    field_type: str
    description: str | None = None
    required: bool = False
    unique: bool = False
    indexed: bool = False
    max_length: int | None = None
    default_value: str | None = None
    enum_values: list[str] | None = None
    reference_bo_code: str | None = None
    is_searchable: bool = False
    sort_order: int = 0

    @field_validator("field_type")
    @classmethod
    def validate_field_type(cls, v):
        valid = [
            "text", "integer", "float", "boolean",
            "date", "datetime", "email", "url",
            "enum", "json", "reference",
        ]
        if v not in valid:
            raise ValueError(f"field_type must be one of {valid}")
        return v


class FieldResponse(BaseModel):
    id: int
    code: str
    name: str
    field_type: str
    description: str | None
    required: bool
    unique: bool
    indexed: bool
    max_length: int | None
    enum_values: list[str] | dict | None
    reference_bo_code: str | None
    is_searchable: bool
    sort_order: int

    model_config = {"from_attributes": True}


class WorkflowStateCreate(BaseModel):
    code: str
    name: str
    color: str | None = None
    is_final: bool = False
    sort_order: int = 0


class WorkflowTransitionCreate(BaseModel):
    code: str
    name: str
    from_state: str
    to_state: str
    conditions: dict | None = None
    webhook_url: str | None = None


class WorkflowCreate(BaseModel):
    initial_state: str
    states: list[WorkflowStateCreate]
    transitions: list[WorkflowTransitionCreate]


class BODefinitionCreate(BaseModel):
    code: str
    name: str
    description: str | None = None
    module_code: str | None = None
    icon: str | None = None
    parent_bo_code: str | None = None
    display_field: str | None = None
    fields: list[FieldCreate] = []
    workflow: WorkflowCreate | None = None


class BODefinitionResponse(BaseModel):
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
