# LLM Calls & Multi-Agent Orchestration

> Conventions introduced by story-1008 (multi-agent orchestration). Read before
> adding any non-stream LLM call, a new Agent role, or touching the chat tool loop.

---

## 1. Non-stream LLM calls: single entry point

**All** non-stream chat completions MUST go through `app/services/llm_client.py::chat`.
Never hand-roll `httpx.AsyncClient` + `/chat/completions` again (the old copies in
`memory.py::_chat` and `query_rewrite.py` were migrated; do not reintroduce the pattern).

What the client gives you for free:

- timeout = `min(provider.timeout_seconds, timeout_cap)` — always pass a node-level
  `timeout_cap` so auxiliary calls can't eat the main-chain latency budget
- retry: exactly once on 5xx / network error; **never retry on timeout** (aligns with
  `stream_chat`; a retried timeout doubles billing)
- optional structured output: `schema=` (Pydantic validation, tolerant `{}`-extraction)
  + `json_mode=True` (protocol-side `response_format`); prompt must still instruct JSON
- optional Langfuse `trace_generation` (pass `trace_id` + `trace_name`)
- failures raise (`ModelCallError` / `ModelTimeoutError` / `LLMStructureError`) —
  the **caller** decides the degradation path; the client never silently swallows errors

Streaming with tools stays on `openai_compatible.stream_chat` (native `delta.tool_calls`
channel). Do NOT generate tool arguments via JSON-schema prompts — parameters at plan
time don't exist yet (tools haven't run), and the native channel is strictly more
reliable (Decision B4).

## 2. Agent role pattern (router / planner / reviewer)

A role = `AgentRole` (`services/agents/roles.py`): name + system prompt + output schema
+ `run()` via llm_client. Every new role on the main chat chain must replicate the
three-piece pattern established by `query_rewrite`:

1. **Degradation** — failure falls back to the pre-existing behavior, never raises to the user
2. **Billing** — usage goes through `cost.accumulate_usage` + one `UsageRecord` row per call;
   write `model` as `"{model}[{role}]"` (e.g. `deepseek-chat[router]`) so reports can split
   Agent overhead with a `LIKE` query
3. **Tracing** — `langfuse_tracing.trace_generation` with the role name as span name

Prompt-injection parity: every role whose input includes retrieved content must (a) wrap
that content with `wrap_evidence()` (`<<<RETRIEVED_DATA>>>`) and (b) include
`DATA_NOT_INSTRUCTION` in its system prompt. Supplementary retrieval results must pass
`injection.scan_chunks` before entering the evidence set.

## 3. `messages.tool_call` — three coexisting payloads

The JSON column now holds three shapes; readers MUST discriminate before parsing:

| Shape | Written when | Recognized by |
|---|---|---|
| `{"id","name","args"}` (optionally `+ "agent_steps":[...]`) | assistant message `pending_confirm` | `api/tools.py` confirm endpoint reads `name`/`args` only — do NOT rename these keys |
| `{"name","auto":true}` / `{"name","args","approved"}` | role=tool result messages | history rendering |
| `{"kind":"agent_steps","steps":[...]}` | orchestrated assistant message `complete` | `steps_from_trace()` — also accepts the `agent_steps` key on the pending_confirm shape |

Adding a fourth shape without a discriminator key is forbidden.

## 4. SSE event ordering contract

`agent_step*` may appear **before** `citation*` (Router decides top_k before retrieval).
The contract is: `agent_step* -> citation* -> agent_step* -> delta* -> (tool_call -> done) | (usage -> done) | error`.
Frontend merges a `running` step with its terminal counterpart by `agent + step_type`;
emit a `running` event before any Agent node call that takes >200ms so users never
stare at a silent bubble.

## 5. Feature flags & degradation equivalence

All orchestration capabilities are opt-in (`llm_router_enabled`,
`agent_orchestration_enabled`, default `False`). With a flag off — or on node failure —
behavior must equal the pre-orchestration pipeline byte-for-byte. Guard this with
regression tests rather than review discipline; `AGENT_TOKEN_BUDGET` counts Agent-node
tokens only (planner/reviewer/router), never the final answer stream.

## 6. Evaluating Router/orchestration changes

`eval_runner` config-group scan uses explicit `top_k` and therefore **cannot** measure
routing decisions. Use the `router_ab` run option (L2 heuristic vs L4 Router on the same
dataset, gold-hit-rate + fallback-rate). Note: local Python 3.14 venv cannot run
fastembed (onnxruntime DLL) — run evals in the Docker image where onnxruntime works.
