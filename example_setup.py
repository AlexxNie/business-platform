"""Beispiel: So konfiguriert ein AI-Agent die Plattform.

Dieses Script zeigt wie per API ein komplettes CRM-Modul
mit Kunden, Deals und Pipeline aufgebaut wird.

Ausfuehren: python example_setup.py
(Voraussetzung: API laeuft auf localhost:8000)
"""

import httpx
import json

BASE = "http://localhost:8000/api/v1"


def main():
    client = httpx.Client(base_url=BASE)

    # 1. Modul erstellen
    print("=== Modul: CRM ===")
    r = client.post("/schema/modules", json={
        "code": "crm",
        "name": "Customer Relationship Management",
        "description": "Kunden, Deals und Pipeline verwalten",
        "icon": "users",
    })
    print(f"  Module: {r.status_code}")

    # 2. BO: Company
    print("\n=== BO: Company ===")
    r = client.post("/schema/definitions", json={
        "code": "Company",
        "name": "Unternehmen",
        "module_code": "crm",
        "display_field": "name",
        "fields": [
            {"code": "name", "name": "Firmenname", "field_type": "text", "required": True, "is_searchable": True},
            {"code": "industry", "name": "Branche", "field_type": "enum",
             "enum_values": ["tech", "manufacturing", "services", "retail", "other"]},
            {"code": "website", "name": "Website", "field_type": "url"},
            {"code": "employees", "name": "Mitarbeiter", "field_type": "integer"},
            {"code": "address", "name": "Adresse", "field_type": "text"},
            {"code": "notes", "name": "Notizen", "field_type": "text"},
        ],
    })
    print(f"  Company BO: {r.status_code}")
    if r.status_code == 201:
        print(f"  Table: {r.json()['table_name']}")

    # 3. BO: Contact (mit Reference auf Company)
    print("\n=== BO: Contact ===")
    r = client.post("/schema/definitions", json={
        "code": "Contact",
        "name": "Kontakt",
        "module_code": "crm",
        "display_field": "name",
        "fields": [
            {"code": "name", "name": "Name", "field_type": "text", "required": True, "is_searchable": True},
            {"code": "email", "name": "E-Mail", "field_type": "email", "unique": True},
            {"code": "phone", "name": "Telefon", "field_type": "text"},
            {"code": "position", "name": "Position", "field_type": "text"},
            {"code": "company_id", "name": "Unternehmen", "field_type": "reference",
             "reference_bo_code": "Company", "indexed": True},
        ],
    })
    print(f"  Contact BO: {r.status_code}")

    # 4. BO: Deal (mit Workflow/Pipeline)
    print("\n=== BO: Deal (mit Pipeline-Workflow) ===")
    r = client.post("/schema/definitions", json={
        "code": "Deal",
        "name": "Deal / Opportunity",
        "module_code": "crm",
        "display_field": "title",
        "fields": [
            {"code": "title", "name": "Titel", "field_type": "text", "required": True, "is_searchable": True},
            {"code": "value", "name": "Wert (EUR)", "field_type": "float"},
            {"code": "company_id", "name": "Unternehmen", "field_type": "reference",
             "reference_bo_code": "Company", "indexed": True},
            {"code": "contact_id", "name": "Kontakt", "field_type": "reference",
             "reference_bo_code": "Contact", "indexed": True},
            {"code": "expected_close", "name": "Erwarteter Abschluss", "field_type": "date"},
            {"code": "probability", "name": "Wahrscheinlichkeit (%)", "field_type": "integer"},
        ],
        "workflow": {
            "initial_state": "lead",
            "states": [
                {"code": "lead", "name": "Lead", "color": "#94a3b8", "sort_order": 0},
                {"code": "qualified", "name": "Qualifiziert", "color": "#3b82f6", "sort_order": 1},
                {"code": "proposal", "name": "Angebot", "color": "#f59e0b", "sort_order": 2},
                {"code": "negotiation", "name": "Verhandlung", "color": "#8b5cf6", "sort_order": 3},
                {"code": "won", "name": "Gewonnen", "color": "#22c55e", "is_final": True, "sort_order": 4},
                {"code": "lost", "name": "Verloren", "color": "#ef4444", "is_final": True, "sort_order": 5},
            ],
            "transitions": [
                {"code": "qualify", "name": "Qualifizieren", "from_state": "lead", "to_state": "qualified"},
                {"code": "send_proposal", "name": "Angebot senden", "from_state": "qualified", "to_state": "proposal"},
                {"code": "negotiate", "name": "Verhandeln", "from_state": "proposal", "to_state": "negotiation"},
                {"code": "win", "name": "Gewonnen", "from_state": "negotiation", "to_state": "won"},
                {"code": "lose_from_qualified", "name": "Verloren", "from_state": "qualified", "to_state": "lost"},
                {"code": "lose_from_proposal", "name": "Verloren", "from_state": "proposal", "to_state": "lost"},
                {"code": "lose_from_negotiation", "name": "Verloren", "from_state": "negotiation", "to_state": "lost"},
            ],
        },
    })
    print(f"  Deal BO: {r.status_code}")
    if r.status_code == 201:
        print(f"  Table: {r.json()['table_name']}")
        print(f"  Fields: {len(r.json()['fields'])}")

    # 5. Testdaten erstellen
    print("\n=== Testdaten ===")

    r = client.post("/data/Company", json={
        "name": "Richardt Tore GmbH",
        "industry": "manufacturing",
        "employees": 25,
        "address": "Rinteln",
    })
    company_id = r.json().get("id") if r.status_code == 201 else None
    print(f"  Company: {r.status_code} (ID: {company_id})")

    if company_id:
        r = client.post("/data/Contact", json={
            "name": "Max Mustermann",
            "email": "max@richardt-tore.de",
            "position": "Geschaeftsfuehrer",
            "company_id": company_id,
        })
        contact_id = r.json().get("id") if r.status_code == 201 else None
        print(f"  Contact: {r.status_code} (ID: {contact_id})")

        r = client.post("/data/Deal", json={
            "title": "Torwartung Jahresvertrag 2026",
            "value": 45000.0,
            "company_id": company_id,
            "contact_id": contact_id,
            "probability": 70,
        })
        deal_id = r.json().get("id") if r.status_code == 201 else None
        print(f"  Deal: {r.status_code} (ID: {deal_id}, State: {r.json().get('_state')})")

        # Workflow-Transition: lead -> qualified
        if deal_id:
            r = client.post(f"/data/Deal/{deal_id}/transitions/qualify")
            print(f"  Transition qualify: {r.status_code} (New state: {r.json().get('_state')})")

    # 6. Introspection
    print("\n=== Platform Overview ===")
    r = client.get("/introspect/overview")
    overview = r.json()
    print(f"  Modules: {overview['stats']['modules']}")
    print(f"  BO Definitions: {overview['stats']['bo_definitions']}")
    print(f"  Total Fields: {overview['stats']['total_fields']}")

    # 7. Suggestions
    print("\n=== AI Suggestions ===")
    r = client.get("/introspect/suggest")
    for s in r.json().get("suggestions", []):
        print(f"  [{s['type']}] {s['message']}")

    print("\nDone! Open http://localhost:8000/docs for Swagger UI")


if __name__ == "__main__":
    main()
