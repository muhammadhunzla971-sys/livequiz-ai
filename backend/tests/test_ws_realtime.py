"""End-to-end realtime tests: a real uvicorn server on a free port, real WebSocket clients."""

import asyncio
import json
import socket
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
import pytest_asyncio
import uvicorn
from sqlalchemy import select
from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed

from app.db.session import get_sessionmaker
from app.models import Answer, GameSession, SessionPlayer
from tests.fakes import make_q


class Server:
    def __init__(self, port: int) -> None:
        self.port = port

    @property
    def http(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    @property
    def ws(self) -> str:
        return f"ws://127.0.0.1:{self.port}"


@pytest_asyncio.fixture
async def server(app) -> AsyncIterator[Server]:  # type: ignore[no-untyped-def]
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    cfg = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", lifespan="on")
    srv = uvicorn.Server(cfg)
    task = asyncio.create_task(srv.serve())
    for _ in range(200):
        if srv.started:
            break
        await asyncio.sleep(0.02)
    assert srv.started
    yield Server(port)
    srv.should_exit = True
    await asyncio.wait_for(task, timeout=15)


class Client:
    """Thin wrapper that records messages and can wait for a given event type."""

    def __init__(self, ws: ClientConnection) -> None:
        self.ws = ws
        self.inbox: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.seen: list[dict[str, Any]] = []
        self.close_code: int | None = None
        self._task = asyncio.create_task(self._pump())

    async def _pump(self) -> None:
        try:
            async for raw in self.ws:
                msg = json.loads(raw)
                self.seen.append(msg)
                await self.inbox.put(msg)
        except ConnectionClosed:
            pass
        finally:
            self.close_code = self.ws.close_code if self.ws.close_code is not None else 1006

    async def send(self, typ: str, **payload: Any) -> None:
        await self.ws.send(json.dumps({"v": 1, "type": typ, "payload": payload}))

    async def wait(self, typ: str, timeout: float = 8.0) -> dict[str, Any]:  # noqa: ASYNC109
        async def _inner() -> dict[str, Any]:
            while True:
                msg = await self.inbox.get()
                if msg["type"] == typ:
                    return msg

        return await asyncio.wait_for(_inner(), timeout)

    async def wait_closed(self, timeout: float = 5.0) -> int:  # noqa: ASYNC109
        await asyncio.wait_for(asyncio.shield(self._task), timeout)
        assert self.close_code is not None
        return self.close_code

    async def close(self) -> None:
        await self.ws.close()
        await asyncio.wait_for(self._task, 5)


async def ws_open(url: str) -> Client:
    return Client(await connect(url, open_timeout=5))


@pytest_asyncio.fixture
async def http(server: Server) -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(base_url=server.http, timeout=10) as c:
        yield c


@pytest_asyncio.fixture
async def teacher(http: httpx.AsyncClient) -> dict[str, str]:
    r = await http.post(
        "/api/auth/register",
        json={"email": "t@example.com", "password": "correct-horse-battery", "display_name": "T"},
    )
    return {"Authorization": f"Bearer {r.json()['access_token']}", "raw": r.json()["access_token"]}


async def make_session(
    http: httpx.AsyncClient, teacher: dict[str, str], n: int = 2, **settings: Any
) -> dict[str, Any]:
    hdr = {"Authorization": teacher["Authorization"]}
    quiz = {"title": "Live", "topic": "Geo", "questions": [make_q(i) for i in range(n)]}
    for q in quiz["questions"]:
        q["time_limit_sec"] = 30
    r = await http.post("/api/quizzes", json=quiz, headers=hdr)
    assert r.status_code == 201, r.text
    quiz_out = r.json()
    r = await http.post("/api/sessions", json={"quiz_id": quiz_out["id"], **settings}, headers=hdr)
    assert r.status_code == 201, r.text
    return {**r.json(), "quiz": quiz_out}


async def join(http: httpx.AsyncClient, pin: str, nick: str, **extra: Any) -> httpx.Response:
    return await http.post("/api/join", json={"pin": pin, "nickname": nick, **extra})


async def open_host(server: Server, sess: dict[str, Any], teacher: dict[str, str]) -> Client:
    host = await ws_open(f"{server.ws}/ws/host/{sess['id']}?token={teacher['raw']}")
    await host.wait("room.state")
    return host


async def open_player(server: Server, joined: dict[str, Any]) -> Client:
    p = await ws_open(f"{server.ws}/ws/player/{joined['room_id']}?token={joined['player_token']}")
    await p.wait("room.state")
    return p


def correct_ids(sess: dict[str, Any], index: int) -> list[str]:
    return list(sess["quiz"]["questions"][index]["correct_option_ids"])


async def test_full_game_three_players(
    server: Server, http: httpx.AsyncClient, teacher: dict[str, str]
) -> None:
    sess = await make_session(http, teacher, n=2)
    host = await open_host(server, sess, teacher)
    joined = []
    players = []
    for nick in ("ann", "bob", "cat"):
        j = (await join(http, sess["pin"], nick)).json()
        joined.append(j)
        players.append(await open_player(server, j))
    await host.wait("player.joined")

    await host.send("host.start")
    shows = [await p.wait("question.show") for p in players]
    q0 = shows[0]["payload"]
    assert "correct_option_ids" not in json.dumps(q0)  # the answer is never sent early
    assert q0["question_end_at"] > q0["server_time"]

    good = correct_ids(sess, 0)
    wrong = [o["id"] for o in q0["options"] if o["id"] not in good][:1]
    await players[0].send("player.answer", question_id=q0["question_id"], option_ids=good)
    await players[1].send("player.answer", question_id=q0["question_id"], option_ids=good)
    await players[2].send("player.answer", question_id=q0["question_id"], option_ids=wrong)
    assert (await players[0].wait("answer.ack"))["payload"]["accepted"] is True

    # Everyone answered, so the question closes early and the answer is revealed.
    reveal = (await players[0].wait("answer.reveal"))["payload"]
    assert reveal["you"]["is_correct"] is True and reveal["you"]["points"] > 0
    loser = (await players[2].wait("answer.reveal"))["payload"]
    assert loser["you"]["is_correct"] is False and loser["you"]["points"] == 0
    assert good[0] in reveal["correct_option_ids"]

    await host.send("host.next")  # -> leaderboard
    lb = (await host.wait("leaderboard.update"))["payload"]
    assert len(lb["entries"]) == 3
    await host.send("host.next")  # -> question 2
    q1 = (await players[0].wait("question.show"))["payload"]
    assert q1["index"] == 1
    await host.send("host.skip")  # close without answers
    await host.wait("answer.reveal")
    await host.send("host.next")
    await host.send("host.next")
    fin = (await players[0].wait("game.finished"))["payload"]
    assert [e["nickname"] for e in fin["podium"]][2] == "cat"

    # Results are archived to Postgres/SQLite.
    for _ in range(50):
        async with get_sessionmaker()() as db:
            gs = await db.get(GameSession, __import__("uuid").UUID(sess["id"]))
            if gs and gs.status == "finished":
                break
        await asyncio.sleep(0.1)
    async with get_sessionmaker()() as db:
        assert gs is not None and gs.status == "finished"
        ranks = (await db.scalars(select(SessionPlayer.final_rank))).all()
        assert sorted(r for r in ranks if r) == [1, 2, 3]
        assert len((await db.scalars(select(Answer))).all()) == 3
        assert gs.settings["questions_played"] == 2  # q2 was shown but skipped with no answers
    for c in (host, *players):
        await c.close()


async def test_duplicate_and_late_answers(
    server: Server, http: httpx.AsyncClient, teacher: dict[str, str]
) -> None:
    sess = await make_session(http, teacher)
    host = await open_host(server, sess, teacher)
    j1 = (await join(http, sess["pin"], "ann")).json()
    j2 = (await join(http, sess["pin"], "bob")).json()
    p1, p2 = await open_player(server, j1), await open_player(server, j2)
    await host.send("host.start")
    q = (await p1.wait("question.show"))["payload"]
    good = correct_ids(sess, 0)

    await p1.send("player.answer", question_id=q["question_id"], option_ids=good)
    assert (await p1.wait("answer.ack"))["payload"]["accepted"] is True
    await p1.send("player.answer", question_id=q["question_id"], option_ids=["A"])
    dup = (await p1.wait("answer.ack"))["payload"]
    assert dup["accepted"] is False

    await p1.send("player.answer", question_id="not-the-question", option_ids=good)
    assert (await p1.wait("answer.ack"))["payload"]["reason"] == "wrong_question"

    await host.send("host.skip")  # question closes while bob never answered
    await p2.wait("answer.reveal")
    await p2.send("player.answer", question_id=q["question_id"], option_ids=good)
    late = (await p2.wait("answer.ack"))["payload"]
    assert late["accepted"] is False and late["reason"] in ("not_active", "late")
    for c in (host, p1, p2):
        await c.close()


async def test_pause_resume_blocks_answers(
    server: Server, http: httpx.AsyncClient, teacher: dict[str, str]
) -> None:
    sess = await make_session(http, teacher)
    host = await open_host(server, sess, teacher)
    p = await open_player(server, (await join(http, sess["pin"], "ann")).json())
    await host.send("host.start")
    q = (await p.wait("question.show"))["payload"]
    await host.send("host.pause")
    paused = (await p.wait("game.paused"))["payload"]
    assert paused["remaining_ms"] > 0
    await p.send("player.answer", question_id=q["question_id"], option_ids=correct_ids(sess, 0))
    assert (await p.wait("answer.ack"))["payload"]["reason"] == "paused"
    await host.send("host.resume")
    resumed = (await p.wait("game.resumed"))["payload"]
    assert resumed["question_end_at"] > resumed["server_time"]
    await p.send("player.answer", question_id=q["question_id"], option_ids=correct_ids(sess, 0))
    assert (await p.wait("answer.ack"))["payload"]["accepted"] is True
    for c in (host, p):
        await c.close()


async def test_player_reconnect_keeps_score_and_answer(
    server: Server, http: httpx.AsyncClient, teacher: dict[str, str]
) -> None:
    sess = await make_session(http, teacher)
    host = await open_host(server, sess, teacher)
    j = (await join(http, sess["pin"], "ann")).json()
    j2 = (await join(http, sess["pin"], "bob")).json()
    p = await open_player(server, j)
    await open_player(server, j2)
    await host.send("host.start")
    q = (await p.wait("question.show"))["payload"]
    await p.send("player.answer", question_id=q["question_id"], option_ids=correct_ids(sess, 0))
    await p.wait("answer.ack")
    await p.close()  # drop the connection mid-question

    again = await ws_open(f"{server.ws}/ws/player/{j['room_id']}?token={j['player_token']}")
    snap = (await again.wait("room.state"))["payload"]
    assert snap["state"] == "question_active"
    assert snap["my_answer"]["answered"] is True
    assert "correct_option_ids" not in json.dumps(snap["question"])
    await again.close()
    await host.close()


async def test_auth_and_roles_are_enforced_server_side(
    server: Server, http: httpx.AsyncClient, teacher: dict[str, str]
) -> None:
    sess = await make_session(http, teacher)
    opener = await open_host(server, sess, teacher)  # host opens the lobby so joining works
    j = (await join(http, sess["pin"], "ann")).json()
    await opener.close()

    bad = await ws_open(f"{server.ws}/ws/host/{sess['id']}?token=garbage")
    assert await bad.wait_closed() == 4401
    as_player = await ws_open(f"{server.ws}/ws/host/{sess['id']}?token={j['player_token']}")
    assert await as_player.wait_closed() == 4401  # a player token is not a host token

    other = (
        await http.post(
            "/api/auth/register",
            json={
                "email": "o@example.com",
                "password": "correct-horse-battery",
                "display_name": "O",
            },
        )
    ).json()["access_token"]
    not_host = await ws_open(f"{server.ws}/ws/host/{sess['id']}?token={other}")
    assert await not_host.wait_closed() == 4403

    missing = await ws_open(f"{server.ws}/ws/host/nope?token={teacher['raw']}")
    assert await missing.wait_closed() == 4404

    p = await open_player(server, j)
    await p.send("host.start")  # players cannot send host commands
    assert (await p.wait("error"))["payload"]["code"] == "forbidden"
    await p.close()


async def test_illegal_transitions_rejected(
    server: Server, http: httpx.AsyncClient, teacher: dict[str, str]
) -> None:
    sess = await make_session(http, teacher)
    host = await open_host(server, sess, teacher)
    await host.send("host.next")
    assert (await host.wait("error"))["payload"]["code"] == "illegal_transition"
    await host.send("host.start")  # nobody has joined yet
    assert (await host.wait("error"))["payload"]["code"] == "no_players"
    await host.send("host.resume")
    assert (await host.wait("error"))["payload"]["code"] == "illegal_transition"
    await host.close()


async def test_kick_and_lock(
    server: Server, http: httpx.AsyncClient, teacher: dict[str, str]
) -> None:
    sess = await make_session(http, teacher)
    host = await open_host(server, sess, teacher)
    j = (await join(http, sess["pin"], "troll")).json()
    p = await open_player(server, j)
    await host.send("host.kick", player_id=j["player_id"])
    assert (await p.wait("player.kicked"))["payload"]["reason"]
    assert await p.wait_closed() == 4410
    again = await ws_open(f"{server.ws}/ws/player/{j['room_id']}?token={j['player_token']}")
    assert await again.wait_closed() in (4410, 4404)
    assert (await join(http, sess["pin"], "troll")).status_code == 403  # nickname now banned

    await host.send("host.lock", locked=True)
    await host.wait("room.state")
    r = await join(http, sess["pin"], "late")
    assert r.status_code == 403 and r.json()["detail"]["code"] == "locked"
    await host.close()


async def test_join_validation_and_pin_lockout(
    server: Server, http: httpx.AsyncClient, teacher: dict[str, str]
) -> None:
    sess = await make_session(http, teacher)
    host = await open_host(server, sess, teacher)  # opens the lobby
    assert (await join(http, sess["pin"], "ann")).status_code == 200
    assert (await join(http, sess["pin"], "ANN")).status_code == 409  # case-insensitive unique
    assert (await join(http, sess["pin"], "f.u.c.k")).status_code == 422  # profanity filter
    assert (await join(http, sess["pin"], "  ")).status_code == 422

    # same device returns to the same player instead of creating a new one
    a = (await join(http, sess["pin"], "dev", device_id="device-1")).json()
    b = (await join(http, sess["pin"], "other", device_id="device-1")).json()
    assert b["rejoined"] is True and b["player_id"] == a["player_id"]

    wrong = "000000" if sess["pin"] != "000000" else "111111"
    codes = [(await join(http, wrong, "x")).status_code for _ in range(11)]
    assert codes[0] == 404 and codes[-1] == 429  # PIN brute-force lockout
    await host.close()


async def test_join_before_lobby_open_and_qr(
    server: Server, http: httpx.AsyncClient, teacher: dict[str, str]
) -> None:
    sess = await make_session(http, teacher)
    r = await join(http, sess["pin"], "early")
    assert r.status_code == 409 and r.json()["detail"]["code"] == "not_open"
    qr = await http.get(f"/api/join/qr/{sess['pin']}.svg")
    assert qr.status_code == 200 and qr.headers["content-type"] == "image/svg+xml"
    assert sess["join_url"].endswith(f"/join?pin={sess['pin']}")


async def test_many_players_broadcast_latency(
    server: Server, http: httpx.AsyncClient, teacher: dict[str, str]
) -> None:
    """Smoke-level perf check: 40 players all receive question.show promptly."""
    sess = await make_session(http, teacher)
    host = await open_host(server, sess, teacher)
    players = []
    for i in range(40):
        j = (await join(http, sess["pin"], f"p{i}")).json()
        players.append(await open_player(server, j))
    await host.send("host.start")
    t0 = asyncio.get_running_loop().time()
    shows = await asyncio.gather(*(p.wait("question.show") for p in players))
    elapsed = asyncio.get_running_loop().time() - t0
    assert len(shows) == 40
    assert elapsed < 2.0
    await asyncio.gather(*(c.close() for c in (host, *players)))


@pytest.mark.parametrize("size", [5000])
async def test_oversized_message_closes_socket(
    server: Server, http: httpx.AsyncClient, teacher: dict[str, str], size: int
) -> None:
    sess = await make_session(http, teacher)
    host = await open_host(server, sess, teacher)
    await host.ws.send("x" * size)
    assert await host.wait_closed() == 1009
