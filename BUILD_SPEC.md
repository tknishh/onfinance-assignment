# BUILD_SPEC: UML Studio (v2)

This is the implementation spec for the AI agent that builds the project. Work through **section 12 (Build order)** top to bottom. Each step ends with an acceptance check that must pass before you move on. If this spec and the code disagree, the spec wins. The exception is anything marked **EXISTS**: that code is already written and tested, and it should only be changed where this spec says so.

---

## 0. Goal

UML Studio is a chat application. The user describes a software system, and the app generates a consistent set of UML diagrams as PlantUML, rendered to SVG. After that, the user can keep chatting to change the output.

- **Stack:** a Next.js 15 frontend (shadcn/ui) that talks to a FastAPI backend through one streaming chat endpoint.
- **Backend:** uses Groq (`openai/gpt-oss-120b` and `openai/gpt-oss-20b`) and Kroki for rendering, and stores everything in SQLite.
- **Feedback:** stored as ART-compatible trajectories for offline RL training.
- **Startup:** the whole stack starts with **one command**:

```bash
docker compose up --build      # then open http://localhost:3000
```

The app supports these cases:

1. **A new user sends a request.** The app builds a shared design model, generates all requested diagrams in parallel, and saves them as v1.
2. **An existing user sends a follow-up.** An intent router decides what the message means:
   - `revise`: change the design.
   - `edit_diagrams`: change only the named diagrams.
   - `add_diagrams`: add diagram types.
   - `remove_diagrams`: remove diagram types.
   - `question`: answer without regenerating.
   - `new_design`: start a new conversation.

   Every change creates version vN+1.
3. **An existing user gives feedback.** Thumbs up/down and a comment are stored as a reward on the matching trajectories. "Apply as revision" sends the comment as a follow-up message.

The minimum input contract is still accepted, both as the first chat message and through `POST /generate`:

```json
{ "prompt": "...", "diagram_types": ["sequential", "component"] }
```

---

## 1. Final file tree

Files marked NEW are created in this phase, EDIT means modify, DELETE means remove, and EXISTS means keep as it is.

```
onfinance-assignment/
  api.py                         EDIT   FastAPI app: /chat SSE + REST
  core/
    __init__.py                  EXISTS
    config.py                    EXISTS
    db.py                        EDIT   add columns to _migrate
    models.py                    EDIT   Message table, new columns
    schemas.py                   EDIT   ChatRequest, FollowUpIntent, timeline schemas
    diagram_types.py             EXISTS
    design_model.py              EXISTS shared design model (consistency)
    prompts.py                   EDIT   intent + answer prompts
    intent.py                    NEW    classify_followup, answer_question, compose_prompt
    examples.py                  NEW    SEBI_EXAMPLE, DEFAULT_KINDS
    llm.py                       EXISTS
    tracing.py                   EXISTS
    cache.py                     EXISTS
    validator.py                 EXISTS
    renderer.py                  EXISTS
    generator.py                 EDIT   run_parallel supports async callbacks
    orchestrator.py              EDIT   handle_chat + generalized update flow
    feedback.py                  EXISTS
    repository.py                EDIT   messages, timeline, delete conversation
  training/                      EXISTS
  tests/
    test_diagram_types.py        EXISTS
    test_validator.py            EXISTS
    test_design_model.py         EXISTS
    test_orchestrator.py         EDIT   keep passing after refactor
    test_intent.py               NEW
    test_chat_api.py             NEW
  web/                           NEW    Next.js app (section 8)
  app.py                         DELETE (Streamlit)
  .streamlit/                    DELETE
  Dockerfile                     DELETE (replaced by Dockerfile.api)
  Dockerfile.api                 NEW
  .dockerignore                  NEW
  docker-compose.yml             EDIT
  requirements.txt               EDIT   remove streamlit packages
  .env.example                   EXISTS
  README.md                      EDIT
  BUILD_SPEC.md                  this file
```

---

## 2. What already exists (EXISTS) and must keep working

Read these files before editing. This section summarises their public API.

### Config (`core/config.py`)

`get_settings()` returns these fields: `groq_api_key`, `gen_provider`, `gen_model=openai/gpt-oss-120b`, `fast_model=openai/gpt-oss-20b`, `llm_base_url`, `llm_api_key`, `reasoning_effort`, `gen_max_tokens`, `temperature`, `max_concurrency`, `max_repair_attempts`, `kroki_url`, `kroki_fallback_url`, `db_url`, `cache_dir`, `judge_enabled`.

### LLM layer (`core/llm.py`)

- `invoke_structured(role: "gen"|"fast", schema, messages, recorder=None) -> schema`. It tries `json_schema`, then `json_mode`, then raw JSON extraction. It applies the semaphore and retries on 429 responses.
- `check_models() -> dict[str, bool]` makes a network call to Groq.

### Diagram types (`core/diagram_types.py`)

- `DiagramKind` (14 kinds), `get_spec(kind)`, and `normalize_types(raw) -> (kinds, unknown)`.
- Aliases are supported; for example, `sequential` maps to `sequence`.

### Shared design model (`core/design_model.py`)

- `build_design_model(prompt, kinds) -> (DesignModel | None, recorder)`
- `update_design_model(old, old_prompt, new_prompt, kinds) -> (DesignModel | None, recorder)`
- `render_design_context(model, kind) -> str` builds the context injected into every diagram prompt.
- `required_names`, `missing_names(code, model, kind)`, and `kind_signature(model, kind)`. `kind_signature` hashes only the slice of the model that a diagram kind depends on.

### Generator (`core/generator.py`)

- `GeneratedDiagram` dataclass with these fields: `kind, title, plantuml, svg, is_valid, error, attempts, latency_ms, model, reused, reused_from_id, warnings, recorder`.
- `generate_one(prompt, kind, design=None)`
- `update_one(new_prompt, old_prompt, old, change_summary, design=None)`
- `reuse_diagram(old)`
- `run_parallel(tasks, on_done=None)`

### Validator (`core/validator.py`)

`sanitize`, `structural_check`, `validate_and_repair` (Kroki compile check plus up to 2 repairs), and `enforce_consistency` (adds elements missing from the shared model).

### Orchestrator (`core/orchestrator.py`)

- `_new_flow` and `_update_flow`. `_update_flow` reuses a diagram only if the prompt diff marks it unaffected and its `kind_signature` is unchanged.
- `handle_generate(req, on_done)` and `handle_feedback(req)`.
- Tests patch these names *inside `core.orchestrator`*: `generate_one`, `update_one`, `invoke_structured`, `build_design_model`, `update_design_model`. **Keep them imported into `core.orchestrator` under the same names.**

### Feedback (`core/feedback.py`)

`compute_reward(user_rating, syntax_valid, attempts, judge, consistent=True)`, `apply_reward(fb)`, and `judge_async(diagram_id)`.

### Database (`core/db.py`)

- `get_session()` uses `expire_on_commit=False`, so ORM rows can still be read after commit.
- `_migrate()` adds missing columns with `ALTER TABLE`.
- Existing tables: `User`, `Conversation`, `DesignVersion` (has `design_model` JSON), `Diagram` (has `warnings` JSON), `Feedback`, `Trajectory`.

Run `source .venv/bin/activate && pytest -q`. All 17 tests pass today.

---

## 3. Data model changes (`core/models.py`, `core/db.py`)

Add these fields and the new table:

```python
class Conversation(SQLModel, table=True):
    ...
    base_prompt: Optional[str] = None          # the original design description

class DesignVersion(SQLModel, table=True):
    ...
    revisions: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    instruction: Optional[str] = None          # follow-up message that produced this version

class Message(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    conversation_id: int = Field(foreign_key="conversation.id", index=True)
    role: str                                  # "user" | "assistant"
    content: str
    intent: Optional[str] = None               # FollowUpIntent.intent for assistant rows
    version_id: Optional[int] = Field(default=None, foreign_key="designversion.id")
    created_at: datetime = Field(default_factory=utcnow)
```

Extend `_ADDED_COLUMNS` in `core/db.py` with the new columns:

```python
_ADDED_COLUMNS = {
    "conversation": {"base_prompt": "TEXT"},
    "designversion": {"design_model": "JSON", "revisions": "JSON", "instruction": "TEXT"},
    "diagram": {"warnings": "JSON"},
}
```

`SQLModel.metadata.create_all` creates the `message` table automatically.

For legacy rows, `revisions` may be NULL, so always read it as `list(v.revisions or [])`. If `base_prompt` is NULL, fall back to the v1 prompt.

---

## 4. Schemas (`core/schemas.py`)

Add these schemas:

```python
IntentName = Literal["revise", "edit_diagrams", "add_diagrams", "remove_diagrams", "question", "new_design"]

class FollowUpIntent(BaseModel):
    intent: IntentName
    instruction: str                     # the change request restated cleanly; the question text for "question"
    target_kinds: list[str] = Field(default_factory=list)

class ChatRequest(BaseModel):
    user_id: str
    message: str = Field(min_length=1)
    conversation_id: Optional[int] = None
    diagram_types: list[str] = Field(default_factory=list)   # used for first message / hint

class MessageOut(BaseModel):
    id: int
    role: str
    content: str
    intent: Optional[str]
    version_id: Optional[int]
    created_at: datetime

class VersionOut(BaseModel):
    id: int
    version_no: int
    prompt: str
    revisions: list[str]
    instruction: Optional[str]
    change_summary: Optional[str]
    diagram_types: list[str]
    design_model: Optional[DesignModel]
    diagrams: list[DiagramResult]
    created_at: datetime

class ConversationOut(BaseModel):
    id: int
    title: str
    base_prompt: Optional[str]
    latest_version_no: Optional[int]
    created_at: datetime

class TimelineOut(BaseModel):
    conversation: ConversationOut
    messages: list[MessageOut]
    versions: list[VersionOut]

class RenderRequest(BaseModel):
    plantuml: str
```

Also make these changes:

- Add `version_id: Optional[int] = None` to `DiagramResult`, and set it in `_to_result`.
- `GenerateResponse` stays as it is.

---

## 5. Intent routing and answers

### `core/examples.py`

Move `SEBI_EXAMPLE` out of `app.py` and into this file, unchanged. Add:

```python
DEFAULT_KINDS = ["sequence", "component", "class", "activity", "deployment"]
```

### `core/prompts.py`: add four prompt builders

```python
def system_intent() -> str
def user_intent(message: str, current_prompt: str, current_kinds: list[str], design_summary: str) -> str
def system_answer() -> str
def user_answer(question: str, design_context: str, diagrams: list[tuple[str, str]]) -> str
```

The `system_intent` prompt must contain these rules, word for word:

- You classify a follow-up message in an ongoing UML design conversation. Return JSON with `intent`, `instruction`, and `target_kinds`.
- `question` applies when the user asks for an explanation, an opinion, or information, and requests no change. Examples: "why is there a gap analyzer?" and "what does the parser do?".
- `edit_diagrams` applies when the change is explicitly limited to named diagrams. Example: "in the sequence diagram, add retries". Set `target_kinds` to those diagrams.
- `add_diagrams` applies when the user asks for additional diagram types. Examples: "also give me a deployment diagram" and "add state machine". Set `target_kinds` to the new kinds.
- `remove_diagrams` applies when the user asks to drop diagram types. Set `target_kinds` to them.
- `new_design` applies when the message describes a completely different system that is unrelated to the current one.
- `revise` covers any other change to the system: new features, components, integrations, constraints, renames. It is also the default when unsure.
- `instruction` is a self-contained, imperative restatement of the request. It must make sense without the chat history.
- `target_kinds` may only contain these values: class, object, component, composite_structure, deployment, package, profile, use_case, activity, state_machine, sequence, communication, interaction_overview, timing.

The `system_answer` prompt says this:

- You are the architect of this design. Answer the question using the shared design model and diagrams.
- Be concise and use markdown.
- Refer to elements by their exact names.
- If the user seems to want a change, end with one line suggesting a follow-up they could send, for example "Reply with *add retries to the sequence diagram* to apply this."

### `core/intent.py`

```python
def compose_prompt(base: str, revisions: list[str]) -> str:
    if not revisions:
        return base
    numbered = "\n".join(f"{i}. {r}" for i, r in enumerate(revisions, 1))
    return f"{base}\n\nRevisions (apply all, later ones win):\n{numbered}"

def design_summary(model: DesignModel | None) -> str:
    """One paragraph: system name, components by layer, data stores, actors. '' if None."""

async def classify_followup(
    message: str, current_prompt: str, current_kinds: list[str], design: DesignModel | None
) -> FollowUpIntent:
    """invoke_structured("fast", FollowUpIntent, ...). Post-process:
       - target_kinds normalized via normalize_types; drop unknowns.
       - edit/add/remove with empty target_kinds -> intent="revise".
       - add_diagrams: drop kinds already present; if none left -> "revise".
       - remove_diagrams: keep only kinds present; if removing all -> "revise".
       - On any exception -> FollowUpIntent(intent="revise", instruction=message, target_kinds=[])."""

async def answer_question(
    question: str, design: DesignModel | None, diagrams: list[tuple[str, str]]   # (kind, plantuml)
) -> str:
    """Plain text call: get_chat("gen").ainvoke([...]) inside llm._get_sem().
       Context: render_design_context(design, DiagramKind.COMPONENT) (or "" if None) + each diagram's
       PlantUML truncated to 3000 chars. Return markdown string. On error return a short apology."""
```

Include a `TrajectoryRecorder("intent", fast_model, prompt_hash(...))` in `classify_followup`. The orchestrator saves its rows with `diagram_id=None`.

---

## 6. Orchestrator refactor (`core/orchestrator.py`)

### 6.1 Callbacks

```python
Emit = Callable[[str, dict], Awaitable[None]]
```

In `core/generator.py`, change `run_parallel` so that `on_done` can be a plain function or a coroutine function:

```python
res = on_done(item)
if inspect.isawaitable(res):
    await res
```

`app.py` is deleted, so the only callers of `run_parallel` are inside `core`.

### 6.2 `_new_flow`

```python
async def _new_flow(user_id, prompt, kinds, unknown, on_done, *,
                    conversation_id: int | None = None, on_design: Emit-like | None = None) -> GenerateResponse
```

- If `conversation_id` is None, create a conversation as it does today, and also set `base_prompt=prompt`.
- After `build_design_model`, call `await on_design(design)` if it was passed in.
- Save `revisions=[]` and `instruction=None` on v1.

### 6.3 `_update_flow` (generalized)

```python
async def _update_flow(user_id, conversation_id, prompt, kinds, unknown, on_done, *,
                       mode: Literal["revise", "edit", "add", "remove"] = "revise",
                       instruction: str | None = None,
                       revisions: list[str] | None = None,
                       target_kinds: set[DiagramKind] = frozenset(),
                       on_design=None) -> GenerateResponse
```

The rules for each mode:

| mode | prompt diff (LLM) | design model | which diagrams are regenerated |
|---|---|---|---|
| `revise` | yes (current behaviour) | `update_design_model(old, old_prompt, prompt)` | current rule: diff-affected, plus signature changed, plus no old diagram or old model |
| `edit` | no; `change_summary = instruction` | `update_design_model(...)` | `update_one` for `target_kinds`, plus any kind whose `kind_signature` changed. Reuse the rest |
| `add` | no; `change_summary = f"Added {kinds}"` | unchanged (`design = old_design`, or build one if None) | `generate_one` for `target_kinds` only. Reuse all others |
| `remove` | no; `change_summary = f"Removed {kinds}"` | unchanged | none. Copy forward every remaining kind with `reuse_diagram` |

Requirements that apply to all modes:

- In `edit` and `revise` modes, call `update_one` with `change_summary=instruction or diff.summary`, so the model receives the precise request.
- Call `on_design(design)` once the design is known, before any diagrams are generated.
- Save the new version with `revisions`, `instruction`, `design_model`, and `diagram_types=[k.value for k in kinds]`.
- Keep the existing signature defaults, so that `handle_generate(...)` and the current tests behave exactly as before. With no keywords, mode is `revise` and behaviour is unchanged.

### 6.4 `handle_chat` (new main entry point)

```python
async def handle_chat(req: ChatRequest, emit: Emit) -> None:
```

The algorithm:

1. Call `repo.get_or_create_user(req.user_id)`.
2. **Parse the JSON contract.** If `req.message.strip()` starts with `{`, try `json.loads`. If the result is a dict with a `prompt` key, set `message = data["prompt"]` and `hint_kinds = data.get("diagram_types", [])`. Otherwise, set `hint_kinds = req.diagram_types`.
3. Set `kinds, unknown = normalize_types(hint_kinds or DEFAULT_KINDS)`. If `kinds` is empty, use `DEFAULT_KINDS`.
4. Define the shared helpers:
   - `on_design(d)` emits `"design_model"` with `d.model_dump() if d else None`.
   - `on_done(item)` emits `"diagram"` with `_generated_payload(item)`. That payload contains kind, title, is_valid, error, attempts, latency_ms, reused, warnings, plantuml, and svg.
   - `started(kinds)` emits one `"diagram_started"` event, `{"kind": k.value}`, for each kind about to be generated or reused.
5. **No conversation yet** (`req.conversation_id is None`):
   1. Create the conversation, with `title=message[:60]` and `base_prompt=message`.
   2. Save a user `Message` with the original `req.message`.
   3. Emit `"conversation"` with `{id, title}`.
   4. Emit `"intent"` with `{intent: "new_design", instruction: message, target_kinds: [kinds]}`.
   5. Emit `started(kinds)`.
   6. Call `resp = await _new_flow(..., conversation_id=conv.id, on_design=on_design)`.
   7. Set `summary = f"Generated {len(resp.diagrams)} diagrams"`.
6. **Existing conversation:**
   1. Load `latest`, `prev_kinds`, `revisions`, `base_prompt` (with the fallback from section 3), and `design`.
   2. Save the user `Message`. Emit `"conversation"`.
   3. Call `intent = await classify_followup(message, latest.prompt, prev_kinds, design)` and emit `"intent"`.
   4. Branch on the intent:
      - `question`:
        1. Run `answer = await answer_question(...)`, passing the latest diagrams.
        2. Emit `"answer"` with `{content: answer}`.
        3. Save an assistant `Message` with intent `question` and no `version_id`.
        4. Emit `"done"`, then return. **No new version is created.**
      - `new_design`: create a new conversation, then run the same steps as case 5. The `"conversation"` event carries the new id, so the UI switches to it.
      - `revise`:
        1. Set `revisions = revisions + [intent.instruction]` and `prompt = compose_prompt(base_prompt, revisions)`.
        2. Run `mode="revise"` with `kinds = prev_kinds`.
      - `edit_diagrams`: the revisions append is the same as for `revise` (so later versions keep the change). Run `mode="edit"` with `target_kinds`.
      - `add_diagrams`: `kinds = prev_kinds + targets`, with revisions unchanged, `prompt = latest.prompt`, and `mode="add"`.
      - `remove_diagrams`: `kinds = prev_kinds - targets`, with `mode="remove"`.
   5. Emit `started(...)` for the kinds being processed, then run the flow with `on_done` and `on_design`.
   6. Use `resp.change_summary` as the summary.
7. Save an assistant `Message` with `content=summary`, `intent=...`, and `version_id=resp.version_id`.
8. Emit `"version"` with the full `VersionOut` for `resp.version_id`, built by `repo.version_out(session, version_id)`.
9. Emit `"done"` with `{conversation_id, version_id}`.

`handle_generate` stays in place for `POST /generate` and the current tests.

`handle_feedback` stays in place. Remove its `apply_as_update` regenerate branch. In the UI, "apply as revision" now sends a chat message. The API field can stay and be ignored.

### 6.5 SSE event contract

The frontend relies on this event order and these payloads:

| event | data |
|---|---|
| `conversation` | `{id: int, title: str}` |
| `intent` | `{intent, instruction, target_kinds: str[]}` |
| `design_model` | `DesignModel` JSON or `null` |
| `diagram_started` | `{kind}` (one per kind) |
| `diagram` | `{kind, title, is_valid, error, attempts, latency_ms, reused, warnings, plantuml, svg}` |
| `answer` | `{content: markdown}` |
| `version` | `VersionOut` |
| `error` | `{message}` |
| `done` | `{conversation_id, version_id: int \| null}` |

---

## 7. API (`api.py`)

Replace `@app.on_event("startup")` with a `lifespan` that calls `init_db()`. Keep CORS open; it's harmless behind the proxy. Endpoints:

```
GET    /health                         -> {"ok": true}      cheap; used by the Docker healthcheck. NO Groq call.
GET    /status                         -> {"kroki": bool, "models": check_models()}   (old /health body)
GET    /diagram-types                  -> [{value, category, description}] from REGISTRY
GET    /examples                       -> [{label, prompt, diagram_types}]   (SEBI first + 2 short ones)
GET    /conversations?user_id=...      -> list[ConversationOut]  newest first
DELETE /conversations/{id}?user_id=... -> {"ok": true}  (404 if not owned)
GET    /conversations/{id}/timeline    -> TimelineOut
POST   /chat                           -> text/event-stream (section 6.5)
POST   /generate                       -> GenerateResponse  (unchanged JSON contract)
POST   /feedback                       -> {"ok": true, "feedback_id": int}
POST   /diagrams/{id}/render           -> DiagramResult   body RenderRequest
```

`POST /diagrams/{id}/render` takes over the old Streamlit re-render logic. It does the following:

1. `sanitize`
2. `render_svg`
3. On failure, return HTTP 422 with `{"detail": error}`.
4. On success, save `plantuml`, `svg`, `is_valid=True`, `error=None`, and `warnings` recomputed with `missing_names` against the version's design model.
5. Set every trajectory of that diagram to `metrics.manual_edit=True` and `reward=1.0`.
6. Return the result.

The SSE implementation pattern follows. Use it as written.

```python
@app.post("/chat")
async def chat(req: ChatRequest):
    queue: asyncio.Queue = asyncio.Queue()

    async def emit(event: str, data) -> None:
        await queue.put((event, jsonable_encoder(data)))

    async def worker():
        try:
            await handle_chat(req, emit)
        except Exception as e:  # surface to UI instead of dropping the stream
            await emit("error", {"message": str(e)})
            await emit("done", {"conversation_id": req.conversation_id, "version_id": None})
        finally:
            await queue.put(None)

    task = asyncio.create_task(worker())

    async def stream():
        try:
            while True:
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
                    continue
                if item is None:
                    break
                event, data = item
                yield f"event: {event}\ndata: {json.dumps(data)}\n\n"
        finally:
            if not task.done():
                task.cancel()

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )
```

### Repository additions (`core/repository.py`)

```python
def add_message(session, conversation_id, role, content, intent=None, version_id=None) -> Message
def list_messages(session, conversation_id) -> list[Message]                 # oldest first
def get_conversation(session, conversation_id) -> Conversation | None
def delete_conversation(session, conversation_id) -> None
    # delete in order: trajectories + feedback of its diagrams, diagrams, messages, versions, conversation
def conversation_out(session, conv) -> ConversationOut
def version_out(session, version_id) -> VersionOut
def timeline(session, conversation_id) -> TimelineOut
```

Also update `create_conversation(session, user_id, title, base_prompt=None)` and `create_version(..., revisions=None, instruction=None)`.

### Requirements

- Remove `streamlit` and `streamlit-local-storage` from `requirements.txt`.
- Keep `langchain-openai`.
- Add `pytest` to a new `requirements-dev.txt`.

---

## 8. Frontend (`web/`)

### 8.1 Scaffold (run these exact commands from the repo root)

```bash
npx create-next-app@latest web --ts --tailwind --eslint --app --no-src-dir \
  --import-alias "@/*" --use-npm --turbopack --yes
cd web
npx shadcn@latest init -d
npx shadcn@latest add -y button card tabs textarea badge popover command dialog sheet \
  scroll-area tooltip sonner toggle-group skeleton resizable separator dropdown-menu \
  avatar alert input label switch
npm i @tanstack/react-query @microsoft/fetch-event-source next-themes lucide-react \
  react-zoom-pan-pinch @uiw/react-codemirror react-markdown remark-gfm \
  react-diff-viewer-continued uuid
npm i -D @types/uuid
```

If a prompt still appears, accept the defaults. If shadcn's `init -d` picks a different base color, that's fine.

### 8.2 Config

`web/next.config.ts`:

```ts
import type { NextConfig } from "next";
const nextConfig: NextConfig = {
  output: "standalone",
  compress: false,            // gzip buffers SSE through the proxy
  eslint: { ignoreDuringBuilds: false },
};
export default nextConfig;
```

`web/.env.local.example`: `API_URL=http://localhost:8080`. When running locally without Docker, copy it to `.env.local`.

### 8.3 API proxy (single origin, browser only talks to port 3000)

`web/app/api/[...path]/route.ts`:

```ts
import { NextRequest } from "next/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const API_URL = process.env.API_URL ?? "http://localhost:8080";

async function proxy(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  const { path } = await ctx.params;
  const url = `${API_URL}/${path.join("/")}${req.nextUrl.search}`;
  const hasBody = !["GET", "HEAD"].includes(req.method);
  const upstream = await fetch(url, {
    method: req.method,
    headers: {
      "content-type": req.headers.get("content-type") ?? "application/json",
      accept: req.headers.get("accept") ?? "*/*",
    },
    body: hasBody ? req.body : undefined,
    // @ts-expect-error duplex is required by Node fetch for streamed request bodies
    duplex: hasBody ? "half" : undefined,
    cache: "no-store",
    signal: req.signal,
  });
  const headers = new Headers(upstream.headers);
  headers.delete("content-encoding");
  headers.delete("content-length");
  headers.set("Cache-Control", "no-cache, no-transform");
  headers.set("X-Accel-Buffering", "no");
  return new Response(upstream.body, { status: upstream.status, headers });
}

export { proxy as GET, proxy as POST, proxy as DELETE, proxy as PUT, proxy as PATCH };
```

Every frontend call uses the relative path `/api/...`.

### 8.4 Files

```
web/
  app/
    layout.tsx               Providers (Theme, Query, User), <Toaster/>, Inter font, dark default
    page.tsx                 <AppShell/>
    globals.css              shadcn tokens (from init)
    api/[...path]/route.ts   proxy (8.3)
  components/
    app-shell.tsx            ResizablePanelGroup: Sidebar | Chat | Workspace
    sidebar.tsx
    chat/
      chat-timeline.tsx
      user-bubble.tsx
      assistant-card.tsx
      generation-progress.tsx
      composer.tsx
      diagram-type-picker.tsx
      empty-state.tsx
    workspace/
      diagram-workspace.tsx
      architecture-view.tsx
      diagram-canvas.tsx
      diagram-toolbar.tsx
      code-editor-dialog.tsx
      compare-dialog.tsx
      feedback-bar.tsx
    theme-toggle.tsx
    providers.tsx
  hooks/
    use-user-id.ts
    use-chat-stream.ts
    use-conversations.ts      react-query hooks: conversations, timeline, diagramTypes, examples
  lib/
    types.ts                  TS mirrors of section 4/6.5 schemas
    api.ts                    typed fetch helpers
    svg.ts                    svgToBlobUrl, downloadSvg, downloadPng, downloadText
    utils.ts                  from shadcn (cn)
  Dockerfile
  .dockerignore
```

### 8.5 State and data flow

- **`useUserId()`** reads `localStorage["uml_uid"]`, or creates one with `uuid.v4()` and stores it. It returns `string | null` and stays null until mounted, so there's no server-side rendering mismatch. Queries are enabled only once it has a value.
- **App state:** keep it in `AppShell` with `useState`:
  - `conversationId: number | null`
  - `selectedVersionId: number | null`
  - `selectedTab: "architecture" | DiagramKind`
  - `kinds: string[]`, defaulting to `DEFAULT_KINDS`
  - Pass these down as props, or through a small React context in `providers.tsx`.
- **React Query keys:** `["conversations", uid]`, `["timeline", conversationId]`, `["diagram-types"]`, and `["examples"]`.
- **`useChatStream()`** returns:

```ts
{ send(message: string, opts?: { kinds?: string[] }): Promise<void>; abort(): void;
  live: LiveState | null; isStreaming: boolean }
type LiveState = {
  userMessage: string;
  intent?: { intent: string; instruction: string; target_kinds: string[] };
  designModel?: DesignModel | null;
  diagrams: Record<string, { status: "queued" | "done" | "failed"; data?: DiagramEvent }>;
  answer?: string;
  error?: string;
};
```

  It uses `fetchEventSource("/api/chat", { method: "POST", body: JSON.stringify({ user_id, message, conversation_id, diagram_types }), openWhenHidden: true, onmessage(ev) {...} })`. It reduces the events like this:
  - `conversation`: call `setConversationId(id)` and invalidate the conversations query.
  - `intent`: store it in `live.intent`.
  - `design_model`: store it in `live.designModel`.
  - `diagram_started`: set `diagrams[kind] = { status: "queued" }`.
  - `diagram`: set status to `"done"`, or `"failed"` if `!is_valid`, and keep the data.
  - `answer`: store it in `live.answer`.
  - `version`: write it into the `["timeline", id]` cache with `queryClient.setQueryData` (append or replace in `versions`), then set `selectedVersionId`.
  - `error`: store it in `live.error` and show `toast.error`.
  - `done`: invalidate `["timeline", id]` and `["conversations", uid]`, then clear `live`.
  - Throw inside `onerror` so the library doesn't retry forever. On abort, call `controller.abort()`.

### 8.6 Components (behaviour spec)

**AppShell**
- Desktop layout is a `ResizablePanelGroup direction="horizontal"` with default sizes 18 (sidebar), 42 (chat), and 40 (workspace). The workspace panel is shown only if the current conversation has at least one version or a live stream is running. Otherwise the chat takes the full width.
- Below 1024px, the sidebar becomes a `Sheet` opened from a menu button, and the workspace opens in a `Sheet` from the right when the user clicks a diagram thumbnail.

**Sidebar**
- Logo text "UML Studio" with a small `Workflow` icon.
- A "New design" button. It sets `conversationId=null` and `selectedVersionId=null`, and clears `live`.
- A `ScrollArea` listing the conversations. Each row shows the title truncated to one line and a `Badge` "v{latest_version_no}". The active row is highlighted.
- Each row has a `DropdownMenu` with a "Delete" item. It opens a confirm `Dialog`, then calls `DELETE /api/conversations/{id}?user_id=`, and then invalidates the conversations query.
- The footer shows the user id as a short `Badge` with a copy-to-clipboard tooltip, and the `ThemeToggle`.

**ChatTimeline**
- Build one list from `timeline.messages`, ordered by `created_at`.
  - A user message is rendered as `UserBubble` (right-aligned, muted background, whitespace preserved).
  - An assistant message is rendered as `AssistantCard`.
  - If `live` is set, append the live `UserBubble` plus `GenerationProgress`.
- Auto-scroll to the bottom whenever a new item arrives.

**AssistantCard** takes `message` and the version found with `version_id`:
- **Header:** an intent badge with an icon:
  - `new_design`: "Generated"
  - `revise`: "Revised"
  - `edit_diagrams`: "Edited: {kinds}"
  - `add_diagrams`: "Added: {kinds}"
  - `remove_diagrams`: "Removed: {kinds}"
  - `question`: "Answer"

  The version badge "v{n}" sits next to it.
- **Body:** for a question, `react-markdown` with `remark-gfm`. Otherwise, the change summary plus a responsive grid of diagram thumbnails: an `<img>` of the SVG blob URL, the title, and status dots for valid, consistent, and reused. Clicking a thumbnail selects that version and tab in the workspace.
- A "View architecture" link opens the architecture tab.

**GenerationProgress**
- Shows the intent badge as soon as it arrives.
- Then the line "Shared design model ready" with a check once `design_model` arrives.
- Then a grid with one row per `diagrams[kind]`:
  - `queued` shows a `Skeleton` and a spinner with "Generating {kind}..."
  - `done` shows the thumbnail, latency, and any warnings icon.
  - `failed` shows a red alert with the error.
- For a question, it shows a typing indicator until `answer` arrives, then the markdown.

**Composer** (sticky at the bottom)
- An auto-growing `Textarea`, with min 1 and max 8 rows. The placeholder depends on state: "Describe the software you want to design..." with no conversation, otherwise "Ask a question or describe a change (e.g. add Slack alerts for high-impact gaps)".
- Enter sends, and Shift+Enter inserts a newline. The send button shows a spinner while streaming, and a Stop button calls `abort()`.
- **The left side of the toolbar** depends on whether a conversation exists:
  - With no conversation, it shows a `DiagramTypePicker`: a popover with a command list of the 14 kinds from `/api/diagram-types`, grouped by category with checkmarks, plus the selected kinds as removable chips.
  - With a conversation, it shows a small hint: "Follow-ups are understood automatically: revise, edit a diagram, add/remove diagrams, or ask a question."
- A `Switch` labelled "JSON". When it's on, the textarea is monospace and prefilled with the SEBI JSON. Its value is sent as-is, and the backend parses it.

**EmptyState** (no conversation and no live stream)
- A heading, a one-line explanation, and 3 example cards from `/api/examples`. Clicking a card fills the composer and sets the kinds. It doesn't send automatically.

**DiagramWorkspace** (for the selected version)
- **Header:** a version `Select` listing v1..vN, and the "consistent" badge count, e.g. "5/5 consistent".
- **`Tabs`:** "Architecture" first, then one tab per diagram (the title, with the kind as a tooltip). Tabs scroll horizontally.

**ArchitectureView** (for a `DesignModel`)
- The system name and summary.
- Four card columns: Actors, Components (sub-grouped by layer with the layer as a small heading), Data stores (each showing its technology), and External systems.
- The numbered main flow as a vertical step list, in the form `source → target: message`.
- Domain entities as compact cards showing their attributes.
- A "Download JSON" button.

**DiagramCanvas**
- Uses `TransformWrapper`/`TransformComponent` from `react-zoom-pan-pinch`, with an `<img src={svgBlobUrl}>` on a white rounded background. Use `<img>`, never `dangerouslySetInnerHTML`, so no script can run.
- Controls: zoom in, zoom out, reset, and fit.
- If `!is_valid`, show a destructive `Alert` with the error instead.
- Show each warning as an amber `Alert`.

**DiagramToolbar**
- Badges: valid/invalid, consistent, reused, "{attempts} attempts", "{latency} ms".
- Buttons with tooltips:
  - Copy PlantUML.
  - Download SVG, PNG, or .puml. For PNG, draw the SVG onto a canvas at 2x scale, then call `toBlob`.
  - Edit code, which opens `CodeEditorDialog`.
  - Compare with previous, which opens `CompareDialog` and is disabled for v1 or when the kind is new.

**CodeEditorDialog**
- CodeMirror holding the PlantUML.
- "Render & save" calls `POST /api/diagrams/{id}/render`. On success it updates the timeline cache and shows a success toast. On 422 it shows the error inline.

**CompareDialog**
- Two columns, previous and current, each showing the SVG `<img>`.
- Below them, `ReactDiffViewer` on the PlantUML with `splitView` on.

**FeedbackBar** (under the canvas)
- Thumbs up/down toggle, a comment `Input`, a "Submit" button, and a checkbox "Also apply as a revision".
- Submit calls `POST /api/feedback`. If the checkbox is ticked and the comment isn't empty, it also calls `send(comment)` from `useChatStream`.
- On success, show the toast "Thanks, feedback saved" and reset the form.

### 8.7 Visual style

- Use the shadcn default (neutral) with dark mode as the default (`next-themes`, `attribute="class"`, `defaultTheme="dark"`).
- Use the `Inter` font from `next/font/google`.
- Use `max-w-3xl mx-auto` for chat content.
- Cards get `rounded-xl border bg-card`.
- Diagram backgrounds stay white in both themes, because PlantUML SVGs are light.
- Use subtle `animate-in fade-in` on new items, which comes with the `tw-animate-css` that shadcn installs.
- No emojis anywhere in the UI.

---

## 9. Docker (one command)

### `Dockerfile.api`

```dockerfile
FROM python:3.11-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY core ./core
COPY training ./training
COPY api.py .
RUN mkdir -p data/cache
EXPOSE 8080
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=12 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health', timeout=3)"
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8080"]
```

### `web/Dockerfile`

```dockerfile
FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:22-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0
COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
EXPOSE 3000
CMD ["node", "server.js"]
```

If `web/public` doesn't exist, create it with a `.gitkeep` so the COPY works.

### `docker-compose.yml`

```yaml
services:
  kroki:
    image: yuzutech/kroki
    restart: unless-stopped

  api:
    build:
      context: .
      dockerfile: Dockerfile.api
    env_file:
      - path: .env
        required: false
    environment:
      KROKI_URL: http://kroki:8000
    volumes:
      - ./data:/app/data
    ports:
      - "8080:8080"
    depends_on:
      - kroki
    restart: unless-stopped

  web:
    build: ./web
    environment:
      API_URL: http://api:8080
    ports:
      - "3000:3000"
    depends_on:
      api:
        condition: service_healthy
    restart: unless-stopped
```

Do not add `GROQ_API_KEY` to `environment`. In compose, `environment` overrides `env_file`, so a line such as `GROQ_API_KEY: ${GROQ_API_KEY:-}` would replace the key from `.env` with an empty string whenever the shell variable isn't set. The key comes only from `.env`. The README tells the user to `cp .env.example .env` and set `GROQ_API_KEY` before running `docker compose up --build`.

### `.dockerignore` (repo root)

```
.venv
web
data
.git
**/__pycache__
.pytest_cache
*.md
```

### `web/.dockerignore`

```
node_modules
.next
.env*.local
```

---

## 10. Tests

All tests use mocks and need no network. Run them with `pytest -q`.

`tests/test_intent.py`:
- `compose_prompt("base", [])` returns `"base"`. With two revisions, the result contains the numbered list.
- `classify_followup` post-processing, with `core.intent.invoke_structured` patched to return a raw `FollowUpIntent`:
  - `edit_diagrams` with empty targets becomes `revise`.
  - `add_diagrams` drops kinds that already exist.
  - When the patched function raises an exception, the result is `revise` with `instruction == message`.

`tests/test_orchestrator.py` (EDIT):
- Keep the 3 existing tests passing.
- Add `handle_chat` tests. In each one, collect the emitted events into a list, and patch `core.orchestrator.classify_followup`, `generate_one`, `update_one`, `build_design_model`, and `update_design_model`.
  - **The first message:** the event order starts `conversation`, `intent`, `design_model`, `diagram_started`... and contains `diagram` x N, then `version`, then `done`. A user message and an assistant message are saved.
  - **The `question` intent:** emits `answer` (with `core.orchestrator.answer_question` patched) and `done`, with `version_id` None. No new `DesignVersion` is created.
  - **The `add_diagrams` intent:** only the new kind goes through `generate_one`, and the others are reused.
  - **The `remove_diagrams` intent:** the new version has one fewer diagram and no LLM calls are made.
  - **The `revise` intent:** `DesignVersion.revisions` contains the instruction, and `prompt == compose_prompt(base, revisions)`.

`tests/test_chat_api.py`:
- Use `fastapi.testclient.TestClient(app)` and patch `api.handle_chat` with a fake that emits 3 events.
- POST `/chat` and read `response.text`. Assert that it contains `event: intent` and `event: done`.
- `GET /health` returns `{"ok": true}`.

---

## 11. README updates

- **Quick start:** `cp .env.example .env`, set `GROQ_API_KEY`, run `docker compose up --build`, open http://localhost:3000. API docs are at http://localhost:8080/docs.
- **Local development without Docker:** run `uvicorn api:app --reload --port 8080` in one terminal, and `cd web && cp .env.local.example .env.local && npm run dev` in another. Kroki can come from `docker compose up kroki`, or the app falls back to kroki.io.
- **Follow-ups section:** explain the intent table, with one example message for each intent.
- Keep the consistency and RL sections, and drop every mention of Streamlit.

---

## 12. Build order (with acceptance checks)

Run Python commands with `source .venv/bin/activate`. If the venv is missing, create it: `python3 -m venv .venv && pip install -r requirements.txt -r requirements-dev.txt`.

1. **Schema and DB:** sections 3 and 4, plus the repository functions in section 7.
   Check: `python -c "from core.db import init_db; init_db()"` succeeds against the existing `data/app.db`. `PRAGMA table_info(conversation)` shows `base_prompt`, and the `message` table exists.
2. **Intent module:** section 5 (`examples.py`, prompts, `intent.py`).
   Check: `pytest -q tests/test_intent.py` passes.
3. **Orchestrator:** section 6, and `run_parallel` handles async callbacks.
   Check: `pytest -q` passes. That includes the existing 17 tests plus the new orchestrator tests.
4. **API:** section 7. Delete `app.py` and `.streamlit/`, and update `requirements.txt`.
   Check: `pytest -q tests/test_chat_api.py` passes. Then `uvicorn api:app --port 8080` starts, and `curl -N -X POST localhost:8080/chat -H 'content-type: application/json' -d '{"user_id":"u1","message":"Design a URL shortener with analytics","diagram_types":["sequence","component"]}'` streams the events and finishes with `event: done`. This needs `GROQ_API_KEY`. If it's missing, skip the curl and note that.
5. **Web scaffold:** sections 8.1 to 8.3.
   Check: `cd web && npm run build` succeeds.
6. **Web components:** sections 8.4 to 8.7.
   Check: `npm run lint && npm run build` pass. Then, with the API running locally and `.env.local` set, `npm run dev` shows the following at http://localhost:3000:
   - The empty state with example cards.
   - Sending the SEBI example streams the progress, then shows the assistant card and the workspace.
   - The follow-up "also add a state machine diagram" gives an "Added" badge.
   - "why is there a gap analyzer?" gives an "Answer" badge with no new version.
   - "add Slack alerts for high-impact gaps" gives "Revised" and v3.
7. **Docker:** section 9. Delete the old `Dockerfile`.
   Check: `docker compose up --build -d`. `docker compose ps` shows api as `healthy` and web running. `curl -s localhost:3000/api/health` returns `{"ok":true}`, and http://localhost:3000 loads. If Docker isn't running, start it (`open -a Docker` on macOS) and wait until `docker info` succeeds.
8. **Docs:** section 11. Check: README quick start matches what you ran.

---

## 13. Known pitfalls

- **SQLAlchemy detached instances:** sessions use `expire_on_commit=False`, but still copy ORM fields into dicts or Pydantic models before leaving `with get_session()` when the data goes to the API response.
- **Tests patch names in `core.orchestrator`:** import `classify_followup` and `answer_question` into the orchestrator with `from core.intent import classify_followup, answer_question`, so the patches take effect.
- **SSE through Next.js:** keep `compress: false`, strip `content-encoding` and `content-length` in the proxy, and never `await upstream.text()` for `/chat`.
- **`fetchEventSource` retries:** it retries on error by default, so throw inside `onerror` to stop.
- **Next 15 route params:** `ctx.params` is a Promise and must be awaited.
- **`useUserId` in server components:** it reads localStorage, so it must only run on the client (`"use client"`, a `useEffect`).
- **Kroki SVGs:** render them with `<img>` and blob URLs. Revoke the URLs on unmount.
- **The Docker healthcheck must not call Groq:** that's why `/health` is cheap and `/status` does the full check.
- **Paths inside the container:** `DB_URL` stays `sqlite:///data/app.db`, which is relative to `WORKDIR /app` and matches the `./data` volume.

---

## 14. Non-goals

- Real authentication. The anonymous UUID stays.
- Token-level streaming of diagram generation. Streaming happens per diagram.
- Online RL training. `training/` stays offline and is unchanged.
