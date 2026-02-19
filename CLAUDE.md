# Business Platform

## Ziel

API-first Plattform, bei der man per REST API beliebige Business Module (CRM, CAFM, HR, ERP...) definiert. Die Engine erstellt automatisch echte PostgreSQL-Tabellen dafuer. Ein "Baukasten" fuer Business-Anwendungen.

## Architektur

```
FastAPI App (async)
├── /api/v1/schema/*      → BO-Definitionen verwalten (Module, BOs, Felder, Workflows)
├── /api/v1/data/*        → Dynamisches CRUD auf alle BO-Tabellen
├── /api/v1/introspect/*  → Plattform-Uebersicht (fuer AI-Agents & Frontend)
│
├── services/schema_service.py  → Kernlogik: BO erstellen, Felder verwalten
├── core/dynamic_tables.py      → CREATE/ALTER/DROP TABLE zur Laufzeit
├── core/field_types.py         → Mapping Feldtyp → PostgreSQL-Spaltentyp
├── core/query_engine.py        → Dynamische Queries mit Filter/Sort/Pagination
├── core/workflow_engine.py     → State Machine (Transitions validieren + ausfuehren)
│
├── models/   → SQLAlchemy Meta-Modelle (Module, BODefinition, FieldDefinition, etc.)
├── schemas/  → Pydantic Request/Response Schemas
└── database.py → Async + Sync Engine Setup
```

## Tech Stack

- Python 3.12, FastAPI 0.115, Uvicorn
- SQLAlchemy 2.0 (async mit asyncpg)
- PostgreSQL 16 (via Docker)
- Redis 7 (via Docker) — noch nicht aktiv genutzt
- Pydantic 2.9, Pydantic-Settings
- Alembic fuer Migrations (Setup vorhanden, keine Migrations generiert)
- Docker Compose fuer alle Services

## Konventionen

- Sprache im Code: Englisch (Kommentare/Docstrings teilweise Deutsch)
- Dynamische Tabellen bekommen Prefix `bo_` (konfigurierbar via `bo_table_prefix`)
- System-Spalten in jeder BO-Tabelle: `id`, `_state`, `_created_at`, `_updated_at`, `_created_by`, `_notes`
- State-Aenderungen nur ueber Workflow-Transitions, nie direkt per PUT
- Feldtypen: text, integer, float, boolean, date, datetime, email, url, enum, json, reference

## API-Struktur

- Schema-API: `/api/v1/schema/modules`, `/api/v1/schema/definitions`, `.../fields`
- Data-API: `/api/v1/data/{bo_code}` — universeller CRUD fuer alle BO-Typen
- Introspect-API: `/api/v1/introspect/overview`, `.../suggest`
- Query-Filter per URL-Params: `field__contains=`, `field__gt=`, `sort=-field`, `page=`, `page_size=`

## Docker

- `docker-compose.yml` mit Services: db (postgres:16-alpine), redis (redis:7-alpine), api
- API laeuft auf Port 8002 (extern) → 8000 (intern)
- DB-Zugangsdaten: bizplatform/bizplatform/bizplatform
- Container sind aktuell NICHT gestartet

## Versionierung

- Aktuelle Version: `1.0.0` (in `app/config.py` → `app_version`)
- Schema: Semantic Versioning — `MAJOR.MINOR.PATCH`
- Bei jeder aenderung die committed und gepusht wird: Minor-Version erhoehen (1.0 → 1.1 → 1.2 ...)
- Workflow bei jedem Push:
  1. `app_version` in `app/config.py` erhoehen
  2. Committen und pushen
  3. GitHub Release erstellen: `gh release create vX.Y.0 --generate-notes`
- GitHub Repo: https://github.com/AlexxNie/business-platform

## Status / Offene Punkte

- Kern-Engine funktionsfaehig (dynamische Tabellen, CRUD, Workflows)
- Auth (passlib + python-jose in deps) — noch nicht implementiert
- Celery Worker — noch nicht implementiert
- Alembic Migrations — noch nicht generiert
- RelationDefinition Model existiert, aber keine API-Endpoints
- Kein Frontend
- Keine Tests
