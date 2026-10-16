# Home-Sec Vision Pipeline: Pi (YOLO) → Server (Qwen3-VL) → Notification

Ollama does not natively support a video file input type over its API. But more importantly for this
project: the Pi is already running YOLO on raw frames, so there's no reason to ever encode those frames
into a video file in the first place. The Pi should send raw JPEG frames straight to the server, which
batches them into a single multi-image request to Qwen3-VL. **Do not round-trip through a video
container** (encode on Pi → decode on server) — it costs CPU on the weak Pi and loses quality for
zero benefit.

---

## 1. Architecture (as originally planned — see note above for what's actually diverged)

```
[Pi: camera + YOLO26n] --(JPEG frames, HTTP POST, fire-and-forget)--> [Server: FastAPI + queue]
                                                                              |
                                                                    single worker loop
                                                                    (GPU can't run 2 jobs at once)
                                                                              |
                                                                     Qwen3-VL-8B-Thinking
                                                                       (Ollama, 3060 Ti)
                                                                              |
                                                                    parse response, dedupe,
                                                                    notify resident if needed
```

- **Pi → Server is async / fire-and-forget.** The Pi POSTs and gets an immediate `202 Accepted`. It does
  not wait on model inference. Inference latency is the server's problem, not the Pi's.
- **Server owns a single-worker queue.** The 3060 Ti (8GB) can only run one 8B-thinking inference at a
  time. Concurrent requests get queued, not fired in parallel — don't `asyncio.gather` multiple
  `llm.ainvoke` calls.
- **Server owns notification.** Once inference completes, the server parses the result and sends the
  text/push notification directly — the Pi is out of the loop after the initial POST.

---

## 2. Prerequisites

```bash
pip install langchain-ollama opencv-python pillow fastapi uvicorn python-multipart requests trycourier
```

```bash
ollama pull qwen3-vl:8b-thinking
```

Confirm current `langchain-ollama` docs for:

- `keep_alive` param — keeps the model resident in VRAM between calls so you're not eating a cold-load
  penalty per event. Behavior/param name has shifted across versions; verify against the version you're
  pinning.
- `num_ctx` — with 8+ image frames plus a system prompt, you can silently exceed Ollama's default 4096
  context (truncation, not an error). Set explicitly and generously; don't rely on the default.

Courier (`trycourier`) is the chosen notification channel — currently email only via `client.send.message`.
Verify constructor/method signatures against your installed version; the fixed `execution_agent.py` uses
`Courier(api_key=...)` and `client.profiles.create(user.id, profile=...)` per current published docs.

---

## 3. Frame Sampling — trigger-centered, not uniform

- [ ] Sample **dense around the YOLO trigger timestamp** instead of uniformly: e.g., a couple frames
      before the trigger, the trigger frame itself, and several after. YOLO already tells you _when_
      the event fired.
- [ ] Keep `max_frames` in the 8–16 range regardless of sampling strategy, to avoid blowing up context /
      VRAM.

---

## 4. Pi side: send raw frames, not a video file

- [ ] Pi captures/samples JPEG frames around the YOLO trigger (see §3) and POSTs them directly as
      multipart form files — no video encoding step.
- [ ] Short request timeout (Pi should not block waiting on inference).
- [ ] Auth token on every request (see §6) — this endpoint accepts footage from inside your house,
      don't leave it open even on a trusted LAN.

```python
# camera_controller.py
import requests

def send_event(camera_id: str, jpeg_bytes_list: list[bytes], server_url: str, token: str):
    files = [("files", (f"frame_{i}.jpg", b, "image/jpeg")) for i, b in enumerate(jpeg_bytes_list)]
    requests.post(
        f"{server_url}/event",
        params={"camera_id": camera_id},
        files=files,
        headers={"x-api-token": token},
        timeout=5,
    )
```

---

## 5. Server side: FastAPI ingestion + queued worker

**Status: not yet reconciled with `execution_agent.py` — see architecture note at top of this file.**

- [ ] `/event` endpoint accepts `camera_id` + JPEG files, validates the auth token, enqueues the job,
      returns immediately.
- [ ] Single background worker consumes the queue one job at a time.
- [ ] Decide: does this FastAPI worker call `run_execution_agent()` directly (simplest — no
      captioning agent exists anymore), or does orchestration move to a LangGraph node instead, with
      this FastAPI layer only handling ingestion? Pick one and update this doc — the code sketch below
      currently just has a TODO placeholder for this.
- [ ] Worker loop wraps inference in try/except — one bad frame batch or a model hiccup must not kill
      the loop.

```python
# execution/action.py — reference sketch, needs reconciling with execution_agent.py's
# synchronous run_execution_agent() call pattern before this is real.
import asyncio
import base64
from fastapi import FastAPI, UploadFile, File, Header, HTTPException

app = FastAPI()
job_queue: asyncio.Queue = asyncio.Queue()

API_TOKEN = "put-a-real-secret-here"  # shared secret between Pi and server

@app.post("/event")
async def receive_event(
    camera_id: str,
    files: list[UploadFile] = File(...),
    x_api_token: str = Header(...),
):
    if x_api_token != API_TOKEN:
        raise HTTPException(status_code=401, detail="bad token")

    frames_b64 = []
    for f in files:
        raw = await f.read()
        frames_b64.append(base64.b64encode(raw).decode("utf-8"))

    await job_queue.put({"camera_id": camera_id, "frames": frames_b64})
    return {"status": "queued"}


async def worker():
    while True:
        job = await job_queue.get()
        try:
            # TODO: call run_execution_agent(
            #     frames_b64=job["frames"], camera_id=job["camera_id"],
            #     timestamp=..., client=client, users=users,
            #     yolo_labels=job.get("yolo_labels"),
            # )
            # No captioning agent step — frames go straight to the VLM.
            pass
        except Exception as e:
            print("inference failed:", e)  # replace with real logging
        finally:
            job_queue.task_done()


@app.on_event("startup")
async def start_worker():
    asyncio.create_task(worker())
```

---

## 6. Auth

- [ ] Shared secret token (`x-api-token` header) required on `/event`. Not open on LAN just because
      it's "internal."
- [ ] Longer term: rotate the token / move to something less naive than a static shared secret if this
      ever leaves the local network.

---

## 7. Response handling & escalation logic

- [x] **Superseded — native tool-calling chosen instead of a JSON output contract.** The execution
      agent has `notify_user` bound as a real tool via `bind_tools()`. `response.tool_calls` is the
      decision, not a JSON blob the model writes. See `execution_agent.py` and `AGENTS.md`.
- [x] The old idea of a model-authored JSON schema (`clip_id`, `tool_called`, `errors`, etc.) is now an
      **audit-log shape populated by orchestration code after the fact** — the model never writes this
      directly. Not yet implemented as actual logging; see open items below.
- [x] Urgency is now an explicit argument on `notify_user` (not a separate output field, not an input
      field), so at least the notify path is auditable. See note below on the no-notify path.
- [ ] Routine notifications go straight from a single `notify_user` tool call — false positives are
      cheap here.
- [ ] Anything wired to an **irreversible or high-stakes action** (auto-lock, alarm dispatch, calling
      authorities) is explicitly OUT OF SCOPE for the execution agent as currently designed — no such
      tools are bound, and `AGENTS.md` says so. If this changes, it needs its own second, independently
      prompted verification step before firing — don't just bind a new tool and trust one model call.
- [ ] The execution agent currently gets **one turn, no visibility into tool results** — it cannot
      "retry another way" despite earlier docs implying it could. `AGENTS.md` has been corrected to
      match this. Decide if a real multi-turn loop (feed tool result back, let model react) is worth
      building, or if single-shot is fine given the only failure mode is "notification didn't send."

---

## 8. Dedup / rate-limiting

- [x] Implemented in `execution_agent.py` as an in-memory `(user_id, camera_id)` cooldown dict — **not**
      the earlier plan of hashing the message text, which would have silently failed to dedupe (the
      model writes different wording every call, so a text-hash key almost never re-matches for the
      same ongoing incident).
- [ ] In-memory only — if this ever runs as more than one process, or restarts frequently, move to
      Redis or a shared table, or cooldown state resets and you lose the protection.
- [ ] Current granularity is per-camera, not per-incident. If you need "don't re-notify about _this
      specific event_" vs. "don't re-notify about _this camera_ for N minutes regardless of cause,"
      you need an explicit incident/clip id threaded through, not just camera_id.

---

## 9. Urgency scoring — now owned entirely by the execution agent

- [x] Confirmed: urgency is **not** supplied upstream. The execution agent computes it itself, 1-9,
      directly from the image frames it's shown (plus YOLO labels as supporting context, not a
      substitute), per a rubric now spelled out in `AGENTS.md`.
- [ ] **No visibility into "decided not to notify" cases.** Right now urgency only gets logged when
      `notify_user` is actually called (urgency > 5). Events scored 1-5 leave zero trace — you can't
      later audit "did the model correctly ignore this, or did it just miss something." Consider a
      second, always-called tool (e.g. `log_assessment(camera_id, urgency, reasoning)`) that fires on
      every frame regardless of the notify decision, so you have a full record to tune the rubric and
      threshold against later. Not implemented yet — deliberately left as a decision for you, since it
      changes the tool surface.
- [ ] The rubric in `AGENTS.md` is a first pass, not validated against real footage. Expect to need
      real examples (a genuine false-positive and false-negative from your own testing) to sharpen the
      boundary between a 5 and a 6, since that boundary is literally the notify/no-notify line.

---

## 10. Performance & processing notes

- **Raw bytes handling:** if frames ever arrive as in-memory `bytes` rather than files on disk, no need
  to write to a temp file at all if you're already ingesting individual JPEGs — just base64-encode
  directly. Only fall back to `tempfile.NamedTemporaryFile` + `cv2.VideoCapture` if you're stuck
  ingesting an actual video container from some other source.
- **Frame count vs. context/VRAM:** keep `max_frames` in the 8–16 range. More frames = more image
  tokens = higher context usage and slower inference, with diminishing returns past this range.
- **Model choice caveat:** Qwen3-VL-8B-Thinking's edge in benchmark scores is on general
  vision-language benchmarks, not validated specifically on judgment quality for this task (urgency
  scoring, notify/no-notify restraint). A/B test Instruct vs. Thinking on your own captured footage
  before fully committing. `EXECUTION_MODEL` must now point at a vision-capable Ollama tag — a
  text-only model will error on the image content blocks `run_execution_agent()` builds.

---

## Open questions / not yet decided

- [x] ~~Resolve the two-agent vs. one-VLM architecture question~~ — resolved: one VLM, no captioning
      agent. See note at top of file.
- [ ] Reconcile the FastAPI/queue design (§5) with `execution_agent.py`'s synchronous call pattern and
      LangGraph hint in its docstring. Pick one orchestration model.
- [ ] Fix the `from types import User` import bug and confirm the real module path.
- [ ] Decide if a real multi-turn tool-result feedback loop is needed for the execution agent, or if
      single-shot is acceptable long-term (see §7).
- [ ] Decide whether an always-called logging tool is needed for full audit coverage, not just the
      notify path (see §9).
- [ ] Verify Courier SDK call signatures (`api_key=`, `profiles.create` positional id, `to` field shape)
      against your actually-installed `trycourier` version — fixed based on current published docs, not
      tested against your environment.
- [ ] Validate and tighten the urgency rubric against real footage, specifically the 5/6 boundary.
