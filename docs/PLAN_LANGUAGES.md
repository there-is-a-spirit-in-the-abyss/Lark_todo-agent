# Language implementation plan

1. Add failing behavior tests for Chinese default, validated instance setting,
   persisted chat selection, real bot replies, model prompts and reminders.
2. Implement the catalog and request-scoped locale; integrate gateway, secretary,
   executor, summaries and background delivery without changing business rules.
3. Add the web selector and catalogs for visible text and API errors; add browser
   regression coverage for English interaction and persisted language choice.
4. Replace deployment-specific onboarding details with generic examples and
   document installation, language commands and verification limits in README.
5. Run the full Python suite, catalog checks, frontend build and browser suite;
   record actual results, skipped integrations and remaining limitations.


Completed local verification (2026-10-16):

- `$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m pytest`:
  130 passed, 2 opt-in PostgreSQL tests skipped, 5 existing SDK warnings.
- `npm --prefix web run test:unit`: 5 passed.
- `npm --prefix web run build`: production build passed.
- `npm --prefix web test`: 11 browser tests passed (test server port 8793).
- `.\.venv\Scripts\python.exe -m pip check`: no broken requirements.
- `.\.venv\Scripts\python.exe -m compileall -q src tests`: passed.

No live model, Feishu OAuth, PostgreSQL service or production deployment was tested.
Dependencies, browser test fixtures/output, runtime caches and database files are
excluded by delivery ignore rules; retained source fixtures were not removed.
