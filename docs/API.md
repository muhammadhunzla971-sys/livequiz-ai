# REST API

Interactive, always up-to-date docs: run the backend and open **`/docs`** (Swagger UI) or
`/openapi.json`. This page is the overview.

Auth: `Authorization: Bearer <access token>` unless marked *public*. Errors are
`{ "detail": "message" }` (or a list of strings for CSV import rows) with the usual status codes:
401 not logged in, 404 not found *or not yours*, 409 conflict, 413 body too large,
422 validation, 429 rate limited (with `Retry-After`), 503 AI unavailable.

## Auth
| Method | Path | Notes |
|---|---|---|
| POST | `/api/auth/register` | *public.* `{email, password (8+), display_name}` → token pair. 10/hour/IP |
| POST | `/api/auth/login` | *public.* 30/min/IP; 8 wrong passwords per account → 15 min lock |
| POST | `/api/auth/refresh` | *public.* Rotates the refresh token |
| POST | `/api/auth/logout` | Revokes the refresh token |
| GET | `/api/auth/me` | Current teacher |

## Quizzes (teacher)
| Method | Path | Notes |
|---|---|---|
| GET | `/api/quizzes` | `?q=&tag=&status=draft\|published` |
| POST | `/api/quizzes` | Manual creation |
| GET / PATCH / DELETE | `/api/quizzes/{id}` | PATCH replaces the question list when `questions` is sent |
| POST | `/api/quizzes/{id}/duplicate` | |
| POST | `/api/quizzes/generate` | AI generation (JSON). 20/hour/teacher |
| POST | `/api/quizzes/generate/stream` | Same, with progress over Server-Sent Events |
| POST | `/api/quizzes/{id}/questions/{qid}/regenerate` | Replace one question |
| GET | `/api/quizzes/{id}/export.csv` | Questions as CSV |
| POST | `/api/quizzes/import` | `{title, topic?, language?, csv}` → new draft. All-or-nothing, errors listed per row |

CSV columns: `type,text,option_a..option_e,correct,explanation,difficulty,subtopic,time_limit_sec,points`
(`correct` like `B` or `A;C`; `type` is `mcq`, `true_false` or `multi_select`).

## Games
| Method | Path | Notes |
|---|---|---|
| POST | `/api/sessions` | `{quiz_id, auto_reveal?, live_leaderboard?, show_distribution?, auto_close?}` → `{id, pin, join_url}` |
| GET | `/api/sessions` , `/api/sessions/{id}` | Your games |
| DELETE | `/api/sessions/{id}` | Delete a finished game and its data |
| GET | `/api/join/{pin}` | *public.* Does this game exist? 60/min/IP |
| GET | `/api/join/qr/{pin}.svg` | *public.* QR code of the join link |
| POST | `/api/join` | *public.* `{pin, nickname, avatar?, device_id?}` → `{room_id, player_id, player_token}`. Wrong-PIN lockout after 10 tries |

## Reports
| Method | Path | Notes |
|---|---|---|
| GET | `/api/reports` | Finished games, newest first |
| GET | `/api/sessions/{id}/report` | Full report JSON |
| GET | `/api/sessions/{id}/report.csv` / `.pdf` | Downloads |
| POST | `/api/sessions/{id}/report/summary` | Generate (or regenerate) the AI summary. 503 if the AI is down; the report itself still works |
| GET | `/api/play/report` | *student token.* Own result and review; 409 until the game is finished |

## Operations
| Path | Notes |
|---|---|
| `GET /health` | process is up |
| `GET /ready` | Postgres and Redis reachable (503 otherwise) |
| `GET /metrics` | Prometheus text; bearer `METRICS_TOKEN` when set |

WebSocket endpoints are documented in [PROTOCOL.md](PROTOCOL.md).
