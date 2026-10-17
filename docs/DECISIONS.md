# Design decisions

Short records of the choices that shaped the project and why.

**1. All live state in Redis, results archived to Postgres.**
Redis gives atomic increments, sorted sets for leaderboards and pub/sub with very low latency.
Keeping state out of process memory means a reconnect, a refresh or a second API instance all see
the same room. Postgres stays the source of truth for anything a teacher reads later.

**2. The server owns time, scoring and roles.**
A browser can be edited, so the client only ever sends "I pick these options". The server stamps
the arrival time, checks the deadline (plus a 500 ms network grace), and computes points
(`base × accuracy × speed × streak`). The clock the client shows is derived from the server's
`question_end_at` and a skew estimate.

**3. First answer wins; resends are harmless.**
Mobile networks retry. Making the handler idempotent (`duplicate` ack) means a retry can never
double-score or change an answer.

**4. Plain WebSocket JSON with a versioned envelope, not Socket.IO.**
Fewer moving parts, works with any client, and the protocol is documented in `PROTOCOL.md`.
`seq` lets a client detect a gap and recover with a snapshot instead of replaying history.

**5. One `room.state` snapshot for every kind of recovery.**
Refresh, reconnect, rejoin on a new device and late join all use the same code path, so there is
one thing to test and nothing "special" about reconnection.

**6. Per-tab device id (sessionStorage), not per-browser.**
Two incognito windows share localStorage, which made two students look like one player. The id
identifies a tab, so a refresh rejoins the same player while a second window is a new student.

**7. Bounded send queue per socket.**
A student on a bad connection must not slow the room. Each connection has its own queue; if it
overflows, that one connection is dropped and can reconnect.

**8. Bounded, blocking Redis pool.**
Found by the load test: unbounded connections exceed managed-Redis limits and fail at ~50 players
per burst. A blocking pool (`REDIS_MAX_CONNECTIONS`) makes operations wait briefly instead.

**9. LLM output is untrusted input.**
Every generated question is validated by the same Pydantic model a teacher's edits go through;
invalid ones are retried with the error message, and the whole batch falls back to a second model.
Nothing from the model is stored without validation. Student answers are never sent to the LLM:
the AI report summary only sees anonymous class totals.

**10. Rate limits in Redis, fixed window.**
Simple, shared across instances, and good enough here. A sliding window or token bucket would be
smoother but not worth the complexity for these limits. (WebSockets use a per-socket token bucket.)

**11. Reports are computed from archived rows and cached.**
Computing once at the end (and on demand) keeps the live path lean. "Questions played" is stored
with the session so a game ended early still reports correctly.

**12. Frontend on Vercel, backend on a container host.**
Vercel cannot proxy WebSockets, so the frontend talks to the API origin directly (`VITE_API_URL`,
CORS allows it). The backend needs a long-lived process, so it ships as a Docker image
(`render.yaml` for Render; any container host works).

**13. Small hand-rolled metrics instead of a metrics library.**
Seven counters and two gauges did not justify a dependency. Output is standard Prometheus text.

**14. Language tools.** React + TypeScript + Vite + Tailwind (fast to build, strict types);
FastAPI + Pydantic v2 (typed end to end, native async and WebSockets); argon2 over bcrypt
(current recommendation); i18next with English and Urdu including right-to-left layout.
