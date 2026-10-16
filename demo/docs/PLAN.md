# Task Tree Demo Implementation Plan

Goal: implement the user-approved project tree rules in an isolated interactive demo.
Architecture: React Flow canvas, Dagre layout, pure immutable domain transitions, versioned browser-local persistence. No production API calls.
Scope: all files and runtime artifacts stay inside /root/huiyang/demo. Existing application and database remain untouched.

## Accepted rules
- Everyone creates projects. Current attached task authors may rename their project.
- Empty never-used roots persist; formerly used roots disappear immediately when empty, including when tasks enter staging.
- Tasks have pending, completed, discarded states; only the immutable author updates state.
- Everyone moves any subtree to staging, any project root, or another task, preserving descendant links and ownership. Cycles are forbidden.
- Delete starts only at one's own task and removes every descendant regardless of author.
- Project completion derives from all attached tasks being completed/discarded. Empty projects are pending.
- Staging survives project deletion and supports cross-project reattachment.

## Execution
- [x] Model: author/states, move/delete/rename/create transitions, validation; tests cover mixed ownership, project cleanup, cross-project moves, cycle rejection, empty roots, terminal-to-pending reversal and persistence.
- [x] UI: desktop/mobile work surface, project sidebar, whole-subtree dragging, staging canvas lane, details panel, accessible alternate move dialog, destructive confirmation listing affected owners, local persistence.
- [x] Verification: unit suite, browser flows and actual dragging at desktop/mobile widths, screenshots, build, isolated preview health, final review.

## Decisions
- Demo uses three switchable mock members and browser-local data; it is not shared multi-user production storage.
- Any task in the active project or staging is a move target, except self/descendants. Move dialog includes other project roots and tasks.
- Non-task root may not be dragged or deleted. Project creators have no special rename rights before they publish a task.
- Task titles/descriptions are editable only by their author; status is reversible among all three states.
- Use native execution and preserve the existing checkout; isolated demo directory is the user's approved boundary.
- Technical choices and implementation already authorized; no additional design approval is needed.

## Verified 2026-10-12

- 18 domain and persistence tests passed.
- 9 Playwright browser tests passed, including real desktop pointer drags,
  selected-node drags, mobile CDP touch drags, cross-project reattachment,
  keyboard dialog operation, ownership checks and corrupted-storage recovery.
- Desktop 1440x950 and mobile 390x844 screenshots inspected.
- Production build passed. React Flow use-client bundler warning is benign.
- Existing Python backend test suite passed all enabled cases; the optional
  real-PostgreSQL test skipped under the existing environment, with existing SDK deprecation warnings.
- Independent read-only code review found no significant outstanding issues.
- Browser runtime libraries were downloaded and extracted inside .cache only.
- Static service serves dist only; local access uses SSH forwarding.
- Original tracked project files remain unchanged; git status shows only demo/.

## Remaining Scope

- Demo persistence is local to each browser origin, not a shared database.
- SSH forwarding must remain connected for local preview access.
- Production integration is intentionally deferred until the user approves the interaction.
