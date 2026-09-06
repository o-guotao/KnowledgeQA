# Technical Design

The app remains a React Router single-page application. `ChatPage` becomes a responsive workspace with a collapsible navigation rail, an accessible mobile drawer, a focused conversation canvas and an optional citation detail panel. A dedicated authenticated `/settings/models` page manages configurations through typed API helpers and Zod schemas.

Tailwind tokens in the existing configuration and reusable UI primitives provide the visual system. Components retain server state locally through existing hooks and request helpers; API keys stay only in controlled form state until submission and are cleared on success/cancel.
