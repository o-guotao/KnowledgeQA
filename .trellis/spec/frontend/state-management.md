# State Management

> How state is managed in this project.

---

## Overview

<!--
Document your project's state management conventions here.

Questions to answer:
- What state management solution do you use?
- How is local vs global state decided?
- How do you handle server state?
- What are the patterns for derived state?
-->

(To be filled by the team)

---

## State Categories

<!-- Local state, global state, server state, URL state -->

(To be filled by the team)

---

## When to Use Global State

<!-- Criteria for promoting state to global -->

(To be filled by the team)

---

## Server State

<!-- How server data is cached and synchronized -->

(To be filled by the team)

---

## Optimistic Streaming vs History Reload (chat)

When a conversation turn streams, the assistant message lives in local state only
until the stream ends. A separate `useEffect` that loads server history for the active
session must never overwrite that list while the turn is in flight.

> **Gotcha**: Backend persists the assistant row as `status="streaming"` **at stream start**
> (before any tokens). A history reload that filters `status !== "streaming"` therefore
> either returns `[]` (request raced the insert) or drops the just-inserted assistant row.
> If that reload result replaces the optimistic list, the streaming placeholder is removed,
> subsequent `delta` events match nothing, and the first answer of a brand-new conversation
> never renders until a later reload (switch away and back) pulls the now-`complete` rows.

Fix shape (`frontend/src/pages/ChatPage.tsx`): register the in-flight turn in a ref
**before** `setActiveId`/optimistic append, skip the history-load effect while
`turnSessionRef.current === activeId`, and clear it in a `finally`:

```ts
turnSessionRef.current = sessionId;          // before setActiveId + setMessages
// load effect: if (turnSessionRef.current === activeId) return;  // trust optimistic
try { await send(...); } finally { if (turnSessionRef.current === sessionId) turnSessionRef.current = null; }
```

---

## Common Mistakes

<!-- State management mistakes your team has made -->

- Letting a `useEffect` on `activeId`/route overwrite optimistic messages that are still
  streaming (see Optimistic Streaming vs History Reload above). Always gate the fetch on
  "no local in-flight turn for this session" and guard stale responses with a cancelled flag.
