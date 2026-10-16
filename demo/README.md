# Huiyang Project Tree Demo

Standalone browser demo in /root/huiyang/demo.
No connection to the production application or database.

## Preview

Use the existing local SSH forward on port 18787.
The remote static server listens on port 8787.
Data is stored per browser and origin; this is not shared multi-user storage.
Switch mock members with the top-right selector.

## Code

- src/model.mjs: immutable operations, permissions, subtree moves and cleanup.
- src/storage.mjs: versioned browser persistence.
- src/layout.mjs: Dagre horizontal tree and staging layout.
- src/App.jsx: React Flow canvas and main user interface.
- src/Nodes.jsx and src/ActionDialog.jsx: graph nodes and dialogs.
- server.mjs: serves only dist.
- docs/PLAN.md: approved requirements and execution record.
- tests: unit and real browser checks.

## Commands

Run npm test and npm run build from this directory.
Run node server.mjs to start the preview if it is not already running.
DEMO_PORT and DEMO_HOST configure its port and address.
The running server immediately serves newly built dist files.

## Integration

The demo uses mock identity and local data by design.
Real integration needs server-side authorization, transactions,
concurrency checks, project membership and persisted staging.
