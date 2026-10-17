# WebSocket protocol v1

Everything real-time goes over two WebSocket endpoints. Payloads below were captured from a real
game against the running server (see `backend/loadtest/` for a client).

## Connecting

| Who | URL | Token |
|---|---|---|
| Teacher (host) | `/ws/host/{session_id}?token=<access JWT>` | the teacher's access token |
| Student | `/ws/player/{room_id}?token=<player JWT>` | `player_token` from `POST /api/join` |

`room_id` and `session_id` are the same id. The token is in the query string because browsers
cannot set headers on a WebSocket; the server redacts `token=` from its logs.

The lobby opens when the host connects. Students joining before that get HTTP 409 (`not_open`).
Join can also fail with `locked`, `full` (300 players), `nickname_taken`, `nickname_banned` or `room_not_found`.

## Envelope

Every message, in both directions:

```json
{ "v": 1, "type": "question.show", "seq": 12, "ts": 1792147587353, "payload": { } }
```

- `v`: protocol version (currently 1).
- `seq`: per-room counter on server messages, always increasing. A client that sees a gap
  reconnects and takes the `room.state` snapshot instead of guessing what it missed.
- `ts`: server clock in milliseconds. Clients use it to estimate clock skew.
- Client messages need only `type` and `payload`.
- Maximum client message size is 4096 bytes (larger closes the socket, code 1009).
  Maximum 10 messages per second per socket (more closes it, code 4429).

## Close codes

| Code | Meaning | Client should |
|---|---|---|
| 4401 | missing/invalid/expired token | go back to join/login |
| 4403 | wrong role or wrong room | stop |
| 4404 | room not found / finished | show "game not found" |
| 4409 | replaced by a newer connection of the same player | stop (another tab took over) |
| 4410 | kicked by the host | stop, show message |
| 4429 | rate limited | back off |
| 1012 | server restarting | reconnect with backoff |
| 1013 | this connection could not keep up and was dropped (slow network) | reconnect; the snapshot catches it up |

## Room states

`created → lobby → question_active → question_closed → leaderboard → question_active → … → finished → archived`,
plus `paused` (from `question_active`). Illegal commands are answered with an `error`
(`illegal_transition`), never ignored silently.

## Server → client events

### `room.state` — full snapshot
Sent on connect and reconnect. This is how a refreshed page gets back to the exact state.
Host version also has `pin` and `players`; a student in an active question also gets `my_answer`,
`you`, and `me` so nothing already submitted is lost.

```json
{ "role": "player", "room_id": "0e50…", "title": "Docs", "state": "lobby", "locked": false,
  "q_index": -1, "total_questions": 2, "players_count": 1, "server_time": 1792147586822,
  "settings": { "auto_reveal": true, "live_leaderboard": false, "show_distribution": true, "auto_close": true } }
```

### `player.joined` / `player.left` / `player.kicked`
```json
{ "player": { "id": "162a…", "nickname": "ana", "avatar": "🦊" }, "count": 1 }
{ "player_id": "162a…", "reason": "disconnected" | "kicked", "count": 1 }
{ "reason": "kicked by host" }
```
`player.kicked` goes only to the kicked student, who is then disconnected with code 4410.

### `game.started`
```json
{ "total_questions": 2 }
```

### `question.show`
The correct answer is never in this message.
```json
{ "index": 0, "total": 2, "question_id": "8707…", "type": "mcq",
  "text": "Which planet is closest to the sun?",
  "options": [{ "id": "A", "text": "Mercury" }, { "id": "B", "text": "Venus" }],
  "time_limit_sec": 10, "points": 1000,
  "started_at": 1792147587352, "question_end_at": 1792147597352, "server_time": 1792147587353 }
```
Clients count down to `question_end_at` (adjusted by clock skew) rather than trusting their own timer.

### `question.tick` — once a second
Host gets the live answer distribution, students only the count:
```json
{ "question_index": 0, "remaining_ms": 9998, "question_end_at": 1792147597352,
  "server_time": 1792147587354, "answered": 0, "distribution": { } }
```

### `answer.ack` — only to the answering student
```json
{ "question_id": "8707…", "accepted": true, "reason": "" }
{ "question_id": "8707…", "accepted": false, "reason": "paused" }
```
Reasons: `late`, `paused`, `not_active`, `wrong_question`, `invalid_option`, `duplicate`.
**The first accepted answer wins**; resending is idempotent and gets `duplicate`.
A short grace period (500 ms) covers network delay for answers sent just before the deadline.

### `question.closed`
```json
{ "question_index": 0, "answered": 2, "total": 2 }
```
Sent when time runs out, everyone has answered, or the host skips.

### `answer.reveal`
Host version:
```json
{ "question_index": 0, "question_id": "8707…", "correct_option_ids": ["A"], "explanation": "",
  "distribution": { "A": 1, "B": 1, "C": 0, "D": 0 }, "answered": 2, "total": 2,
  "correct_count": 1, "avg_response_ms": 1089, "role": "host" }
```
Student version adds a personal result:
```json
{ "…": "…", "role": "player",
  "you": { "answered": true, "chosen": ["A"], "is_correct": true, "accuracy": 1.0,
           "points": 956, "streak": 1, "score": 956, "rank": 1, "rank_change": 1 } }
```

### `leaderboard.update`
`phase` is `live` (during a question, if the host enabled it) or `reveal` (after it).
```json
{ "question_index": 0, "phase": "reveal", "total_players": 2, "is_last": false,
  "entries": [{ "rank": 1, "player_id": "162a…", "nickname": "ana", "avatar": "🦊",
                "score": 956, "streak": 1, "rank_change": 1 }] }
```

### `game.paused` / `game.resumed`
```json
{ "remaining_ms": 9412, "reason": "host", "server_time": 1792147587940 }
{ "question_end_at": 1792147597756, "remaining_ms": 9412, "server_time": 1792147588344 }
```
While paused every answer is refused with `paused`; the question's remaining time is preserved.

### `game.finished`
```json
{ "reason": "completed" | "host_ended", "total_players": 2,
  "podium": [ /* top 3 entries */ ], "leaderboard": [ /* entries */ ],
  "me": { "nickname": "ana", "rank": 1, "score": 956, "correct": 1, "total_questions": 2,
          "accuracy_pct": 50, "best_streak": 1 } }
```
`me` is only in the student version. Results are archived to Postgres right after.

### `error`
```json
{ "code": "illegal_transition", "message": "cannot advance from question_active" }
```
Codes: `bad_message`, `bad_payload`, `forbidden`, `illegal_transition`, `unknown_type`, `room_not_found`,
`no_players`, `no_questions`, `not_revealed`, `not_a_player`, `player_not_found`, `busy`, `internal`.

### `pong`
Reply to `ping`: `{ "client_ts": null, "server_time": 1792147587338 }`.

## Client → server

### Student
| `type` | payload | Notes |
|---|---|---|
| `player.answer` | `{ "question_id": "…", "option_ids": ["A"] }` | 1–5 ids; multi-select sends several |
| `ping` | `{ "client_ts": 1792147587000 }` | keep-alive and skew estimate |

### Host (all rejected with `forbidden` from a student socket)
| `type` | payload | Effect |
|---|---|---|
| `host.start` | `{}` | lobby → first question (`no_players` if nobody joined) |
| `host.next` | `{}` | reveal → leaderboard → next question → finish |
| `host.skip` | `{}` | close the current question now |
| `host.reveal` | `{}` | reveal manually when auto-reveal is off |
| `host.pause` / `host.resume` | `{}` | freeze / continue the clock |
| `host.kick` | `{ "player_id": "…" }` | remove a student, bans their nickname for this room |
| `host.lock` | `{ "locked": true }` | stop new students joining |
| `host.settings` | `{ "auto_reveal": true, "live_leaderboard": false, "show_distribution": true, "auto_close": true }` | any subset |
| `host.end` | `{}` | finish the game early |
| `ping` | `{}` | keep-alive |

## Reconnection

A student who loses connection keeps their score, answer and rank: the player token is valid for
6 hours and the server stores everything in Redis. On reconnect the server sends `room.state`
(with `my_answer` if they already answered) and the clock continues. The web client reconnects with
exponential backoff and re-estimates clock skew each time. A second tab for the same player
replaces the first (close code 4409).
