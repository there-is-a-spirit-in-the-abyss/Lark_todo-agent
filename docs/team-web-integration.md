# Team web integration

Approved scope (2026-10-12): one Feishu group per isolated team space. The
React project-tree demo is the team UI; private chat remains the personal
todo UI. Group messages only return a link when the actual bot is mentioned
and the text contains 团队任务, 团队todo, team tasks or team todo (case insensitive).

All team rules match demo/src/model.mjs: immutable author, three states,
any member moves any subtree, author deletes a whole subtree, cycle checks,
ever-used empty project cleanup, shared staging, derived project completion.
An absent author's tasks are editable by all current members. Returning
members see the latest persisted state; no restoration of earlier versions.
No team deadlines, reminders, weekly summaries or administrator override.

Implementation: FastAPI routes alongside the existing app; independent
team space JSON snapshots in PostgreSQL, transactional version checks,
server-side sessions and one-use OAuth state. Each request verifies current
Feishu group membership, failing closed if Feishu cannot verify membership.
No positive membership cache. Previously displayed data cannot be recalled
from a departed member's device; subsequent requests are denied.

The production frontend is derived from the retained demo under web/.
It uses the same tree layout and dialogs, real members and server snapshots,
polling for changes and rejecting stale writes instead of overwriting them.
Personal records are retained. Legacy team records are retained but excluded
from personal queries and reminders when the new mode is enabled.

Deployment: project-local settings and HTTPS reverse proxy configuration.
Operate inside your own project directory. Do not change system services.
Existing app remains running until verification and rollout prerequisites pass.
Feishu application console permissions and OAuth redirect registration may
require the user's account; do not fake login or use mock identity in production.

## Verification scope

The source includes model, migration, API, routing and browser regression tests.
Run the commands in README in your own checkout. Historical rollout records are
not evidence of this copy's deployment. Real Feishu/OAuth/TLS verification remains
an environment-specific operation.
