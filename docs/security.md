# Security

The Lost Apple App stores Apple credentials, session material, and polling state inside the Home Assistant App data volume. The Lost Apple Integration stores only the local Lost Apple App URL and pairing token.

Do not log or export the following values in plain text:

- Apple IDs
- passwords
- two-factor codes
- session cookies
- session tokens
- pairing tokens
- raw Apple response payloads

Diagnostics redaction should keep credential-like fields out of exported payloads. The current redaction list includes `pairing_token`, `token`, `password`, `apple_id`, and `session`.

The Lost Apple App setup page is intended for Home Assistant Ingress where available. The local API used by the Lost Apple Integration requires a bearer pairing token on every request under `/api/v1/`.
