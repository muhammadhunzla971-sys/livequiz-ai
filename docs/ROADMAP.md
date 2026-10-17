# Roadmap: what is built and what is left

## Level 1 (mandatory): built
Accounts and login · AI quiz generation (plan → generate → validate → retry, live progress) ·
manual quiz editor · quiz library (search, tags, duplicate) · live games with PIN + QR ·
lobby, countdown, timed questions, pause/resume, skip, kick, lock · server-side scoring (speed,
streak, multi-select partial credit) · live leaderboard + podium · reconnect without losing answers ·
student screens (join, play, result, final, answer review, result card) · teacher reports (class,
topic, question and student level; CSV, PDF; AI summary) · English + Urdu (RTL) · dark mode,
keyboard and screen-reader support, reduced motion.

## Level 2 (recommended)
| Item | Status |
|---|---|
| Multi-language generation | **Built** for the quiz language chosen by the teacher (English, Urdu, and others the model supports). Automatic detection of the source language: not built |
| Import / export (CSV) | **Built** (`/api/quizzes/import`, `export.csv`). Kahoot-like format and Google Forms: not built |
| Reuse of quizzes | **Partly**: duplicate a quiz, search and tag the library. No shared question bank |
| Quiz from uploaded material (PDF/DOCX/URL) + RAG with citations | Not built |
| More question types (short answer, ordering, image, fill-in) | Not built (MCQ, true/false, multi-select exist) |
| Team mode, practice / self-paced mode | Not built |
| Power-ups | Not built |
| Co-hosting / sharing quizzes | Not built |

## Level 3 (differentiators)
| Item | Status |
|---|---|
| Observability | **Partly**: request IDs, JSON logs, `/health`, `/ready`, Prometheus `/metrics`. No Grafana dashboard or Sentry |
| Anti-cheat+, adaptive difficulty, agentic workflow, live AI assistant, misconception detection, spaced repetition, LMS / SSO, voice mode, gamification, PWA, admin panel | Not built |

Level 1 was finished and hardened first on purpose; none of the Level 3 items is faked.

## Known limits (honest list)
- The AI summary and quiz generation need a working LLM key. If the model is down the teacher is
  told and can build quizzes by hand; cached quizzes keep working.
- Free hosting sleeps when idle; the first request after a break is slow.
- Load test (`backend/loadtest/ws_load.py`): see README. It was run on one machine against a real
  Redis, not against a deployed server over the internet.
- The Playwright test runs on a live stack (`docker compose up` + dev server); it is part of CI.

## Suggested next steps (in order of value)
1. Generate from uploaded notes (PDF/DOCX) with source citations.
2. Practice (self-paced) mode with a deadline link.
3. Short-answer questions graded by the LLM.
4. Team mode.
5. Grafana dashboard + Sentry.

---

# Requirement checklist

| Area | Status | Where |
|---|---|---|
| Foundation: Docker, config, migrations, auth (argon2, JWT, refresh rotation) | Done | `docker-compose.yml`, `backend/app/core`, `backend/app/api/auth.py` |
| AI generation: provider abstraction, prompts, validation, retries, fallback model, caching, quotas | Done | `backend/app/llm`, `services/quiz_generation.py` |
| Realtime: state machine, WebSocket protocol v1, Redis state and leaderboard, scoring, reconnect | Done | `backend/app/ws`, `services/room_engine.py`, `docs/PROTOCOL.md` |
| Teacher frontend: create/edit, library, launch, host panel | Done | `frontend/src/pages`, `features/host`, `features/quiz-editor` |
| Student frontend: join, lobby, play, results, leaderboard | Done | `features/play`, `pages/Play.tsx` |
| Analytics, reports, AI summaries, CSV/PDF | Done | `services/analytics.py`, `api/reports.py`, `pages/ReportView.tsx` |
| Security: rate limits, moderation, headers, log redaction, prod config guard | Done | `core/rate_limit.py`, `core/net.py`, `services/moderation.py`, `main.py` |
| Accessibility, i18n (en/ur, RTL) | Done | `frontend/src/i18n`, component tests |
| Observability: request id, logs, health, ready, metrics | Done | `core/logging.py`, `core/metrics.py`, `main.py` |
| Backend tests: scoring, state machine, API, WebSocket multi-client, mocked LLM incl. bad JSON | Done (116 tests) | `backend/tests` |
| Frontend component tests | Done (45 tests) | `frontend/src/**/*.test.ts(x)` |
| Playwright end-to-end (1 host + 3 players) | Done | `frontend/e2e/full-game.spec.ts` |
| CI on every push (ruff, mypy, pytest, tsc, eslint, prettier, vitest, build, e2e) | Done | `.github/workflows/ci.yml` |
| Load test + results | Done | `backend/loadtest/ws_load.py`, README |
| Seed script, demo script | Done | `backend/app/seed.py`, README |
| Docs: PROTOCOL, ARCHITECTURE, DECISIONS, ROADMAP, API, DEPLOYMENT | Done | `docs/` |
| Deployment config | Done (Render + Vercel) | `render.yaml`, `frontend/vercel.json`, `docs/DEPLOYMENT.md` |
| `frontend/Dockerfile` | Not done on purpose | The frontend is a static build hosted on Vercel; `npm run dev` is used locally |
| Level 2 / Level 3 advancements | Partial / Not done | see tables above |
