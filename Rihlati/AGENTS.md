# Project continuity

Read `PROJECT_ARCHITECTURE.md` before modifying Rihlati. The user-supplied Word document, copied to `docs/idea.docx`, is the architectural source of truth.

Preserve the learner journey, multilingual chat and audio, FAQs, specialist escalation, ticket replies, and the office dashboard in every feature change. New features extend the complete system.

Never rebuild or delete the live SQLite database. Apply additive migrations and incremental source imports. Keep an auditable source/page for retrieved material and reviewer attribution for learned corrections. Never reuse unreviewed model-generated output as trusted knowledge.

Tests use an isolated temporary database. Clearly distinguish live AI/audio provider calls from local retrieval and mocked tests. Do not publish this loopback-only demo as an authenticated production service.

Current authorized expansion: real member, office, and admin accounts; office approval; multiple staff; member links to at most three approved offices; server-enforced tenant and permission isolation; six languages (ar/en/fil/fr/am/sw). Main admin cannot be deleted, suspended, or demoted. Never commit initial credentials or `.enviroment.local`. Passwords use salted one-way hashes. Preserve legacy records without automatically assigning them to newly registered strangers. The final flowchart and mobile app are deferred until website verification.
