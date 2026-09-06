# Technical Design

Compose remains the local orchestrator, with tagged backend/frontend images configurable by `IMAGE_TAG`. Health checks are added for the backend `/api/healthz` and frontend root. The Jenkins pipeline uses a local Docker-capable agent, injects secrets from Jenkins Credentials, builds tagged images, runs Compose, waits for health, and on failure redeploys the tag stored as `LAST_GOOD_TAG` in a runtime env file excluded from Git.

The pipeline must not assume Jenkins runs in the same container as Docker Desktop; its node configuration must provide Docker CLI access to the Docker Desktop daemon.
