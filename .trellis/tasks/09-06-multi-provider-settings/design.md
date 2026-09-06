# Technical Design

## Data and API

Create a user-owned `model_configs` table with UUID, `user_id`, display name, HTTPS base URL, model name, encrypted API key, timeout, optional price fields, activation flag, timestamps, and a uniqueness rule that permits at most one active config per user. A migration backfills no keys and leaves the environment DeepSeek fallback intact.

Expose authenticated REST endpoints to list, create, update, delete, activate, and test configurations. Ownership is always constrained by the JWT user ID. List/detail responses carry `api_key_masked`, never the ciphertext or plaintext.

## Encryption and validation

Use Fernet authenticated encryption with `MODEL_CONFIG_ENCRYPTION_KEY`; startup validates its format when user-managed configuration is enabled. Decrypt only immediately before the outbound model request. Validation normalizes an HTTPS base URL, strips a trailing slash, prohibits userinfo, and resolves/rejects loopback, private, link-local, multicast, unspecified and reserved IP ranges.

## Chat integration

Refactor the DeepSeek client into a provider-neutral OpenAI-compatible streaming client. Chat resolves the request user's active config, falling back to environment DeepSeek settings only when no user config exists. Existing SSE events, tool calls, timeout behavior, and cost accounting remain unchanged; runtime cost uses the selected config prices when present.
