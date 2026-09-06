# Technical Design

## Boundaries

The parent task integrates three child deliverables. The configuration work must land before final end-to-end verification; UI can consume a stable configuration API once it exists; deployment work consumes final image definitions.

## Cross-cutting decisions

- Model configuration is user-owned, not global. A configuration selects an OpenAI-compatible `/chat/completions` provider and model for that user's chat requests.
- `MODEL_CONFIG_ENCRYPTION_KEY` is an environment/Jenkins secret and is never persisted in Postgres. Each API key is encrypted at rest using authenticated symmetric encryption; all read models return only a mask.
- The existing `DEEPSEEK_*` settings remain a deployment fallback for legacy/demo use. Per-user active configuration takes precedence.
- Current provider/client service is generalized without changing the SSE event contract or RAG/tool flow.
- Image tags use the Jenkins build number plus `current`; deployment keeps the last known-good tag in a local runtime file ignored by Git.

## Integration gates

1. Config migration and protected API pass before UI settings is connected.
2. UI build passes before Docker image build.
3. Compose health and end-to-end smoke pass before Jenkins pipeline acceptance.

## Rollback

- Database migration includes downgrade removing only configuration data.
- Failed Jenkins deployment redeploys the previously recorded image tag; named database/MinIO/model volumes remain intact.
- A configuration failure falls back only when an explicit environment fallback is enabled; it must not silently use another user's provider.
