---
name: M365 Integrator
command: /m365-integrator
description: specialized skill for integrating Microsoft 365 services (Graph API, Auth) into React/Node apps.
type: skill
category: custom
enabled: true
version: v3.0
---

# Microsoft 365 Integration Skill

This skill assists in connecting the application to the Microsoft 365 ecosystem.

## Prerequisite: Azure App Registration

Before coding, ensure an App Registration exists in Azure Portal:
1.  Go to [entra.microsoft.com](https://entra.microsoft.com).
2.  Register a new app.
3.  **Redirect URI (SPA)**: `http://localhost:5173` (for Vite dev).
4.  **API Permissions**: Add `User.Read`, `Calendars.Read`, `Files.Read` (delegated).

## implementation Guide

### 1. Authentication (Frontend)
Use `@azure/msal-react` and `@azure/msal-browser`.

*   **Config Template**: Use `resources/authConfig.ts` to set up the MsalProvider.
*   **Login Flow**: Use the `useMsal` hook to request tokens.

### 2. Calling Graph API
Always use the token acquired via MSAL to authenticate requests.

*   **Client**: Use `@microsoft/microsoft-graph-client`.
*   **Helper**: Use `resources/GraphService.ts` as a wrapper.

## Common Patterns

### Getting User Profile
```typescript
const { instance, accounts } = useMsal();
// ... acquire token ...
const graphClient = Client.initWithMiddleware({ authProvider });
const user = await graphClient.api('/me').get();
```

### Accessing OneDrive
```typescript
const files = await graphClient.api('/me/drive/root/children').get();
```
