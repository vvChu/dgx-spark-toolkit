---
name: idop-crud-generator
description: Agent-driven code generation for CRUD operations in IDOP modules.
---

# IDOP CRUD Generator

This skill leverages the Agent's coding ability to generate full CRUD logic based on templates.

## Workflow

1.  **Identify Schema**: Determine the data structure (e.g., `Product { id, name, price }`).
2.  **Target Module**: Identify where the module lives (e.g., `server/modules/Product`).
3.  **Generate Code**:
    *   Read the templates in `resources/templates/`.
    *   Apply the logic to the target files, replacing placeholders like `{{EntityName}}` or logic for fields.

## Templates

### Backend
*   **Controller**: `resources/templates/controller.js`
    *   Standard `getAll`, `getById`, `create`, `update`, `delete`.
*   **Service**: `resources/templates/service.js`
    *   In-memory array manipulation (Mock DB).

### Frontend
*   **Store**: `resources/templates/store.ts`
    *   Zustand store with async actions calling the API.

## Usage Rule
*   Do NOT just copy-paste. You must **adapt** the template to the specific fields of the requested entity.
*   If the user asks "Create CRUD for Customer", reading these templates is mandatory.
