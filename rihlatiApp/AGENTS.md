# Rihlati mobile continuity

Read ../Rihlati/PROJECT_ARCHITECTURE.md before edits. Preserve the shared learner journey, multilingual chat/audio, FAQs, specialist tickets and office features. The server and database remain in ../Rihlati; never create a second production database or embed secrets in the app.

src/ contains the mobile UI and native integrations. scripts/build.mjs copies an explicit allowlist of shared web logic into www/ and bundles native modules. Do not edit generated www/ files. Admins are blocked by the /app-api/ server surface and scoped sessions, not only hidden UI. Test with isolated databases, never reset or seed real user accounts. No publication or store submission without user approval.
