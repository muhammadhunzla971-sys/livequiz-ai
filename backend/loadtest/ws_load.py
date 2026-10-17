"""Load test: one teacher, N simulated students, a full game over real HTTP + WebSockets.

    python loadtest/ws_load.py --base http://localhost:8000 --players 200 --questions 5

Server needs JOIN_RATE_PER_MIN >= players (all simulated students share one IP).
Measures, over loopback or a real network (the machine clocks must agree, so run it on the
same machine as the API for the first number):
  * broadcast latency: server send time of question.show -> client receive time
  * fan-out spread: first to last player receiving the same question.show
  * answer ack latency: player.answer sent -> answer.ack received
"""

import argparse
import asyncio
import json
import random
import statistics
import time
import uuid

import httpx
import websockets


def pct(values: list[float], p: float) -> float:
    if not values:
        return float("nan")
    s = sorted(values)
    return s[min(len(s) - 1, int(round(p / 100 * (len(s) - 1))))]


def summary(name: str, values: list[float], unit: str = "ms") -> str:
    if not values:
        return f"{name:<28} no data"
    return (
        f"{name:<28} n={len(values):<6} p50={pct(values, 50):7.1f}{unit} "
        f"p95={pct(values, 95):7.1f}{unit} p99={pct(values, 99):7.1f}{unit} "
        f"max={max(values):7.1f}{unit}"
    )


class Stats:
    def __init__(self) -> None:
        self.broadcast: list[float] = []
        self.ack: list[float] = []
        self.shows: dict[str, list[float]] = {}
        self.errors = 0
        self.error_codes: dict[str, int] = {}
        self.connected = 0
        self.unexpected_close = 0
        self.close_reasons: dict[str, int] = {}


def envelope(type_: str, **payload: object) -> str:
    return json.dumps({"v": 1, "type": type_, "payload": payload})


async def player(ws_base: str, joined: dict, stats: Stats, correct_rate: float) -> None:
    url = f"{ws_base}/ws/player/{joined['room_id']}?token={joined['player_token']}"
    sent_at: dict[str, float] = {}
    try:
        async with websockets.connect(url, max_size=2**20) as ws:
            stats.connected += 1
            async for raw in ws:
                msg = json.loads(raw)
                kind, payload = msg["type"], msg.get("payload", {})
                if kind == "question.show":
                    now = time.time() * 1000
                    stats.broadcast.append(now - msg["ts"])
                    stats.shows.setdefault(payload["question_id"], []).append(now)
                    options = [o["id"] for o in payload["options"]]
                    # We don't know the right answer, so "correct_rate" is just a random mix.
                    pick = random.choice(options) if random.random() < correct_rate else options[0]
                    await asyncio.sleep(random.uniform(0.1, 1.0))
                    sent_at[payload["question_id"]] = time.perf_counter()
                    await ws.send(
                        envelope(
                            "player.answer", question_id=payload["question_id"], option_ids=[pick]
                        )
                    )
                elif kind == "answer.ack":
                    q = payload.get("question_id")
                    if q in sent_at:
                        stats.ack.append((time.perf_counter() - sent_at.pop(q)) * 1000)
                elif kind == "error":
                    stats.errors += 1
                    code = str(payload.get("code", "?"))
                    stats.error_codes[code] = stats.error_codes.get(code, 0) + 1
                elif kind == "game.finished":
                    return
    except Exception as exc:
        stats.unexpected_close += 1
        stats.close_reasons[repr(exc)[:80]] = stats.close_reasons.get(repr(exc)[:80], 0) + 1


async def host(
    ws_base: str, session_id: str, token: str, expect_players: int, stats: Stats
) -> None:
    url = f"{ws_base}/ws/host/{session_id}?token={token}"
    async with websockets.connect(url, max_size=2**20) as ws:
        joined = 0
        while joined < expect_players:
            msg = json.loads(await ws.recv())
            joined += msg["type"] == "player.joined"
        for _ in range(600):  # wait until every player's socket is attached (up to 30 s)
            if stats.connected >= expect_players:
                break
            await asyncio.sleep(0.05)
        await ws.send(envelope("host.start"))
        async for raw in ws:
            msg = json.loads(raw)
            kind = msg["type"]
            if kind in ("answer.reveal", "leaderboard.update"):
                await asyncio.sleep(0.2)
                await ws.send(envelope("host.next"))
            elif kind == "game.finished":
                return
            elif kind == "error":
                stats.errors += 1
                code = "host:" + str(msg.get("payload", {}).get("code", "?"))
                stats.error_codes[code] = stats.error_codes.get(code, 0) + 1


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8000")
    ap.add_argument("--players", type=int, default=200)
    ap.add_argument("--questions", type=int, default=5)
    ap.add_argument("--join-concurrency", type=int, default=25)
    args = ap.parse_args()
    ws_base = args.base.replace("https://", "wss://").replace("http://", "ws://")
    stats = Stats()

    async with httpx.AsyncClient(base_url=args.base, timeout=30) as http:
        r = await http.post(
            "/api/auth/register",
            json={
                "email": f"load-{uuid.uuid4().hex[:8]}@example.com",
                "password": "load-test-password",
                "display_name": "Load",
            },
        )
        r.raise_for_status()
        token = r.json()["access_token"]
        auth = {"Authorization": f"Bearer {token}"}
        questions = [
            {
                "type": "mcq",
                "text": f"Load test question number {i + 1}?",
                "options": [{"id": c, "text": f"Option {c} for {i}"} for c in "ABCD"],
                "correct_option_ids": ["A"],
                "time_limit_sec": 10,
            }
            for i in range(args.questions)
        ]
        r = await http.post(
            "/api/quizzes",
            json={"title": "Load test", "topic": "load", "questions": questions},
            headers=auth,
        )
        r.raise_for_status()
        quiz_id = r.json()["id"]
        r = await http.post("/api/sessions", json={"quiz_id": quiz_id}, headers=auth)
        r.raise_for_status()
        session = r.json()

        # The lobby opens when the teacher's socket connects, so the host must be there first.
        host_task = asyncio.create_task(host(ws_base, session["id"], token, args.players, stats))
        await asyncio.sleep(1.0)
        print(f"joining {args.players} players ...")
        sem = asyncio.Semaphore(args.join_concurrency)
        joins: list[dict] = []

        async def join(i: int) -> None:
            async with sem:
                jr = await http.post(
                    "/api/join",
                    json={"pin": session["pin"], "nickname": f"p{i}", "device_id": f"d{i}"},
                )
                jr.raise_for_status()
                joins.append(jr.json())

        t0 = time.perf_counter()
        await asyncio.gather(*(join(i) for i in range(args.players)))
        print(f"  joined in {time.perf_counter() - t0:.1f}s")

        players = [asyncio.create_task(player(ws_base, j, stats, 0.6)) for j in joins]
        t0 = time.perf_counter()  # the host starts the game once every player has attached
        await asyncio.wait_for(host_task, timeout=300)
        await asyncio.wait_for(asyncio.gather(*players), timeout=60)
        elapsed = time.perf_counter() - t0

    spreads = [(max(v) - min(v)) for v in stats.shows.values() if len(v) > 1]
    print(f"\n== {args.players} players, {args.questions} questions, game took {elapsed:.1f}s ==")
    print(summary("broadcast latency (show)", stats.broadcast))
    print(summary("fan-out spread (first->last)", spreads))
    print(summary("answer ack latency", stats.ack))
    print(f"errors received: {stats.errors}   unexpected disconnects: {stats.unexpected_close}")
    for code, n in stats.error_codes.items():
        print(f"  error code {code} x{n}")
    for reason, n in stats.close_reasons.items():
        print(f"  disconnect x{n}: {reason}")
    print(f"acks received: {len(stats.ack)} / {args.players * args.questions} expected")
    print(f"mean broadcast: {statistics.fmean(stats.broadcast):.1f} ms" if stats.broadcast else "")


if __name__ == "__main__":
    asyncio.run(main())
