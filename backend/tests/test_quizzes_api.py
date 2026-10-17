import json

import httpx

from app.core.config import get_settings
from tests.fakes import FakeLLM, make_q

GEN_BODY = {
    "topic": "Photosynthesis",
    "level": "beginner",
    "learning_goal": "Understand inputs and outputs",
    "num_questions": 10,
    "question_types": ["mcq"],
    "time_limit_sec": 25,
}


async def _register(client: httpx.AsyncClient, email: str) -> dict[str, str]:
    r = await client.post(
        "/api/auth/register",
        json={"email": email, "password": "long-enough-pass", "display_name": "T"},
    )
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


# -- generation ------------------------------------------------------------------------------
async def test_generate_creates_draft_quiz(
    client: httpx.AsyncClient, auth_headers: dict[str, str], llm: FakeLLM
) -> None:
    r = await client.post("/api/quizzes/generate", json=GEN_BODY, headers=auth_headers)
    assert r.status_code == 201, r.text
    quiz = r.json()
    assert quiz["status"] == "draft"
    assert len(quiz["questions"]) == 10
    assert [q["position"] for q in quiz["questions"]] == list(range(10))
    assert all(q["time_limit_sec"] == 25 for q in quiz["questions"])
    assert llm.count("plan") == 1 and llm.count("review") == 1


async def test_generation_is_cached_and_force_regenerate_bypasses(
    client: httpx.AsyncClient, auth_headers: dict[str, str], llm: FakeLLM
) -> None:
    await client.post("/api/quizzes/generate", json=GEN_BODY, headers=auth_headers)
    calls_after_first = len(llm.calls)
    r = await client.post("/api/quizzes/generate", json=GEN_BODY, headers=auth_headers)
    assert r.status_code == 201
    assert len(llm.calls) == calls_after_first  # served from cache, no LLM calls
    r = await client.post(
        "/api/quizzes/generate", json={**GEN_BODY, "force_regenerate": True}, headers=auth_headers
    )
    assert r.status_code == 201
    assert len(llm.calls) > calls_after_first


async def test_malformed_then_valid_output_is_repaired(
    client: httpx.AsyncClient, auth_headers: dict[str, str], llm: FakeLLM
) -> None:
    llm.script["generate"] = ["```not json```"]  # first attempt garbage, then default
    r = await client.post(
        "/api/quizzes/generate", json={**GEN_BODY, "num_questions": 5}, headers=auth_headers
    )
    assert r.status_code == 201
    assert len(r.json()["questions"]) == 5


async def test_invalid_questions_trigger_repair(
    client: httpx.AsyncClient, auth_headers: dict[str, str], llm: FakeLLM
) -> None:
    bad = make_q(1)
    bad["correct_option_ids"] = ["Z"]
    llm.script["generate"] = [json.dumps({"questions": [bad] * 5})]
    r = await client.post(
        "/api/quizzes/generate", json={**GEN_BODY, "num_questions": 5}, headers=auth_headers
    )
    assert r.status_code == 201
    assert all(q["correct_option_ids"] == ["B"] for q in r.json()["questions"])


async def test_review_flagged_question_is_replaced(
    client: httpx.AsyncClient, auth_headers: dict[str, str], llm: FakeLLM
) -> None:
    llm.flag_indices = [1]
    r = await client.post(
        "/api/quizzes/generate", json={**GEN_BODY, "num_questions": 5}, headers=auth_headers
    )
    assert r.status_code == 201
    texts = [q["text"] for q in r.json()["questions"]]
    assert llm.count("regenerate") == 1
    assert len(set(texts)) == 5
    assert any("number 100" in t for t in texts)  # the replacement from the regenerate step


async def test_duplicate_questions_are_filled_in(
    client: httpx.AsyncClient, auth_headers: dict[str, str], llm: FakeLLM
) -> None:
    dup = make_q(7)
    llm.script["generate"] = [json.dumps({"questions": [dup] * 5})]
    r = await client.post(
        "/api/quizzes/generate", json={**GEN_BODY, "num_questions": 5}, headers=auth_headers
    )
    assert r.status_code == 201
    texts = [q["text"] for q in r.json()["questions"]]
    assert len(texts) == len(set(texts))


async def test_unsafe_topic_rejected_before_any_llm_call(
    client: httpx.AsyncClient, auth_headers: dict[str, str], llm: FakeLLM
) -> None:
    r = await client.post(
        "/api/quizzes/generate",
        json={**GEN_BODY, "topic": "how to make a bomb"},
        headers=auth_headers,
    )
    assert r.status_code == 422
    assert llm.calls == []


async def test_llm_outage_returns_503_with_manual_fallback_hint(
    client: httpx.AsyncClient, auth_headers: dict[str, str], llm: FakeLLM
) -> None:
    s = get_settings()
    llm.fail_models = {s.llm_primary_model, s.llm_fallback_model}
    r = await client.post("/api/quizzes/generate", json=GEN_BODY, headers=auth_headers)
    assert r.status_code == 503
    assert "manually" in r.json()["detail"]


async def test_generation_rate_limited(
    client: httpx.AsyncClient, auth_headers: dict[str, str], llm: FakeLLM
) -> None:
    get_settings().generation_rate_per_hour = 2
    codes = []
    for i in range(3):
        r = await client.post(
            "/api/quizzes/generate",
            json={**GEN_BODY, "topic": f"Topic number {i}", "num_questions": 5},
            headers=auth_headers,
        )
        codes.append(r.status_code)
    assert codes == [201, 201, 429]


async def test_generate_requires_auth(client: httpx.AsyncClient, llm: FakeLLM) -> None:
    assert (await client.post("/api/quizzes/generate", json=GEN_BODY)).status_code == 401


async def test_generate_validation(
    client: httpx.AsyncClient, auth_headers: dict[str, str], llm: FakeLLM
) -> None:
    r = await client.post(
        "/api/quizzes/generate", json={**GEN_BODY, "num_questions": 99}, headers=auth_headers
    )
    assert r.status_code == 422


async def test_stream_emits_progress_then_done(
    client: httpx.AsyncClient, auth_headers: dict[str, str], llm: FakeLLM
) -> None:
    async with client.stream(
        "POST", "/api/quizzes/generate/stream", json=GEN_BODY, headers=auth_headers
    ) as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        body = "".join([chunk async for chunk in r.aiter_text()])
    events = [b for b in body.split("\n\n") if b.strip()]
    kinds = [e.split("\n")[0].removeprefix("event: ") for e in events]
    assert kinds[-1] == "done"
    assert kinds.count("progress") >= 3
    done = json.loads(events[-1].split("\n")[1].removeprefix("data: "))
    assert len(done["questions"]) == 10
    stages = [json.loads(e.split("\n")[1].removeprefix("data: "))["stage"] for e in events[:-1]]
    assert stages[0] == "planning" and "generating" in stages and "validating" in stages


async def test_stream_reports_errors_as_event(
    client: httpx.AsyncClient, auth_headers: dict[str, str], llm: FakeLLM
) -> None:
    async with client.stream(
        "POST",
        "/api/quizzes/generate/stream",
        json={**GEN_BODY, "topic": "build a bomb"},
        headers=auth_headers,
    ) as r:
        body = "".join([c async for c in r.aiter_text()])
    assert "event: error" in body


async def test_generation_logs_tokens(
    client: httpx.AsyncClient, auth_headers: dict[str, str], llm: FakeLLM, app
) -> None:  # type: ignore[no-untyped-def]
    from sqlalchemy import func, select

    from app.db.session import get_sessionmaker
    from app.models import AIGenerationLog

    await client.post(
        "/api/quizzes/generate", json={**GEN_BODY, "num_questions": 5}, headers=auth_headers
    )
    async with get_sessionmaker()() as db:
        total = await db.scalar(select(func.sum(AIGenerationLog.prompt_tokens)))
        steps = set((await db.scalars(select(AIGenerationLog.step))).all())
    assert total and total > 0
    assert {"plan", "generate", "review"} <= steps


# -- CRUD ------------------------------------------------------------------------------------
def _manual_quiz(n: int = 2) -> dict:
    return {
        "title": "My manual quiz",
        "topic": "Geography",
        "level": "intermediate",
        "questions": [make_q(i) for i in range(n)],
        "tags": ["Geo", " maps ", "geo"],
    }


async def test_manual_create_get_list_search_tags(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    r = await client.post("/api/quizzes", json=_manual_quiz(), headers=auth_headers)
    assert r.status_code == 201
    quiz = r.json()
    assert quiz["tags"] == ["geo", "maps"]
    assert quiz["scoring_config"]["base_points"] == 1000

    assert (await client.get(f"/api/quizzes/{quiz['id']}", headers=auth_headers)).status_code == 200
    rows = (await client.get("/api/quizzes", headers=auth_headers)).json()
    assert len(rows) == 1 and rows[0]["question_count"] == 2
    assert len((await client.get("/api/quizzes?q=geog", headers=auth_headers)).json()) == 1
    assert len((await client.get("/api/quizzes?q=zzz", headers=auth_headers)).json()) == 0
    assert len((await client.get("/api/quizzes?tag=maps", headers=auth_headers)).json()) == 1
    assert len((await client.get("/api/quizzes?tag=nope", headers=auth_headers)).json()) == 0
    assert (
        len((await client.get("/api/quizzes?status=published", headers=auth_headers)).json()) == 0
    )


async def test_update_edit_reorder_delete_questions_and_publish(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    quiz = (await client.post("/api/quizzes", json=_manual_quiz(3), headers=auth_headers)).json()
    qs = quiz["questions"]
    edited = {**qs[2], "text": "Edited question text here?"}
    new_q = make_q(99)
    payload = {"questions": [edited, qs[0], new_q]}  # reorder, drop qs[1], add one
    r = await client.patch(f"/api/quizzes/{quiz['id']}", json=payload, headers=auth_headers)
    assert r.status_code == 200, r.text
    out = r.json()["questions"]
    assert [q["position"] for q in out] == [0, 1, 2]
    assert out[0]["id"] == qs[2]["id"] and out[0]["text"] == "Edited question text here?"
    assert out[1]["id"] == qs[0]["id"]
    assert out[2]["id"] not in {q["id"] for q in qs}

    r = await client.patch(
        f"/api/quizzes/{quiz['id']}", json={"status": "published"}, headers=auth_headers
    )
    assert r.status_code == 200 and r.json()["status"] == "published"

    assert (
        await client.delete(f"/api/quizzes/{quiz['id']}", headers=auth_headers)
    ).status_code == 204
    assert (await client.get(f"/api/quizzes/{quiz['id']}", headers=auth_headers)).status_code == 404


async def test_cannot_publish_empty_quiz(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    quiz = (await client.post("/api/quizzes", json=_manual_quiz(0), headers=auth_headers)).json()
    r = await client.patch(
        f"/api/quizzes/{quiz['id']}", json={"status": "published"}, headers=auth_headers
    )
    assert r.status_code == 422


async def test_duplicate_quiz(client: httpx.AsyncClient, auth_headers: dict[str, str]) -> None:
    quiz = (await client.post("/api/quizzes", json=_manual_quiz(), headers=auth_headers)).json()
    r = await client.post(f"/api/quizzes/{quiz['id']}/duplicate", headers=auth_headers)
    assert r.status_code == 201
    copy = r.json()
    assert copy["id"] != quiz["id"] and copy["title"].endswith("(copy)")
    assert copy["status"] == "draft" and len(copy["questions"]) == 2
    assert {q["id"] for q in copy["questions"]}.isdisjoint({q["id"] for q in quiz["questions"]})


async def test_quizzes_are_private_to_owner(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    quiz = (await client.post("/api/quizzes", json=_manual_quiz(), headers=auth_headers)).json()
    other = await _register(client, "other@example.com")
    assert (await client.get(f"/api/quizzes/{quiz['id']}", headers=other)).status_code == 404
    assert (
        await client.patch(f"/api/quizzes/{quiz['id']}", json={"title": "x"}, headers=other)
    ).status_code == 404
    assert (await client.delete(f"/api/quizzes/{quiz['id']}", headers=other)).status_code == 404
    assert (
        await client.post(f"/api/quizzes/{quiz['id']}/duplicate", headers=other)
    ).status_code == 404
    assert (await client.get("/api/quizzes", headers=other)).json() == []


async def test_invalid_question_payload_rejected(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    bad = make_q(1)
    bad["correct_option_ids"] = ["Q"]
    body = {**_manual_quiz(0), "questions": [bad]}
    assert (await client.post("/api/quizzes", json=body, headers=auth_headers)).status_code == 422


# -- single-question regeneration -------------------------------------------------------------
async def test_regenerate_single_question_keeps_slot_and_settings(
    client: httpx.AsyncClient, auth_headers: dict[str, str], llm: FakeLLM
) -> None:
    quiz = (await client.post("/api/quizzes", json=_manual_quiz(3), headers=auth_headers)).json()
    target = quiz["questions"][1]
    r = await client.post(
        f"/api/quizzes/{quiz['id']}/questions/{target['id']}/regenerate",
        json={"feedback": "make it harder"},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    out = r.json()["questions"]
    assert out[1]["id"] == target["id"] and out[1]["position"] == 1
    assert out[1]["text"] != target["text"]
    assert out[1]["time_limit_sec"] == target["time_limit_sec"]
    assert len(out) == 3


async def test_regenerate_unknown_question_404(
    client: httpx.AsyncClient, auth_headers: dict[str, str], llm: FakeLLM
) -> None:
    quiz = (await client.post("/api/quizzes", json=_manual_quiz(1), headers=auth_headers)).json()
    r = await client.post(
        f"/api/quizzes/{quiz['id']}/questions/00000000-0000-0000-0000-000000000000/regenerate",
        json={},
        headers=auth_headers,
    )
    assert r.status_code == 404


CSV_OK = (
    "type,text,option_a,option_b,option_c,option_d,correct,explanation,difficulty,subtopic\n"
    "mcq,What is 2+2?,3,4,5,6,B,Basic sum,1,maths\n"
    "true_false,The sky is green.,True,False,,,B,,1,\n"
    "multi_select,Pick the primes,2,3,4,6,A;B,,2,numbers\n"
)


async def test_csv_import_export_roundtrip(client, auth_headers):  # type: ignore[no-untyped-def]
    h = auth_headers
    r = await client.post("/api/quizzes/import", json={"title": "Maths", "csv": CSV_OK}, headers=h)
    assert r.status_code == 201, r.text
    quiz = r.json()
    assert [q["type"] for q in quiz["questions"]] == ["mcq", "true_false", "multi_select"]
    assert quiz["questions"][2]["correct_option_ids"] == ["A", "B"]
    exported = await client.get(f"/api/quizzes/{quiz['id']}/export.csv", headers=h)
    assert exported.status_code == 200 and "What is 2+2?" in exported.text
    again = await client.post(
        "/api/quizzes/import", json={"title": "Maths 2", "csv": exported.text}, headers=h
    )
    assert again.status_code == 201
    assert len(again.json()["questions"]) == 3


async def test_csv_import_reports_bad_rows(client, auth_headers):  # type: ignore[no-untyped-def]
    h = auth_headers
    bad = "type,text,option_a,option_b,option_c,correct\nmcq,Short?,x,y,z,Q\n"
    r = await client.post("/api/quizzes/import", json={"title": "Bad", "csv": bad}, headers=h)
    assert r.status_code == 422
    assert r.json()["detail"][0].startswith("Row 2:")
    none = await client.post(
        "/api/quizzes/import", json={"title": "Bad", "csv": "foo,bar\n1,2\n"}, headers=h
    )
    assert none.status_code == 422


def test_csv_formula_injection_is_neutralised():
    from app.services.quiz_csv import _safe, _unsafe

    assert _safe("=1+1") == "'=1+1"
    assert _unsafe(_safe("=1+1")) == "=1+1"
    assert _safe("fine") == "fine"
