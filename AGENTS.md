# Project continuity

The active application now lives in `Rihlati/`. Make all application changes there. Preserve existing top-level presentation and competition documents. Read `Rihlati/PROJECT_ARCHITECTURE.md` before modifying the application.

Read `PROJECT_ARCHITECTURE.md` before modifying Rihlati. The user-supplied Word document `أساس هيكلة الفكرة.docx` is the architectural source of truth.

Preserve the learner journey, multilingual chat and audio, FAQs, specialist escalation, ticket replies, and the office dashboard in every feature change. New features extend the complete system.

Never rebuild or delete the live SQLite database. Apply additive migrations and incremental source imports. Keep an auditable source/page for retrieved material and reviewer attribution for learned corrections. Never reuse unreviewed model-generated output as trusted knowledge.

Tests use an isolated temporary database. Clearly distinguish live AI/audio provider calls from local retrieval and mocked tests. Do not publish this loopback-only demo as an authenticated production service.
