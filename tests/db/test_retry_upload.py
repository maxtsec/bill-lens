from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from hashlib import sha256
import json
from threading import Barrier, Event, Lock, local
from time import monotonic
from uuid import UUID

from fastapi.testclient import TestClient
import httpx2
from openai import OpenAI
import pytest
from sqlalchemy import create_engine, event, select, text
from sqlalchemy.orm import Session

from bill_lens.api import service
from bill_lens.api.app import create_app, get_extractor
from bill_lens.contract import ExpectedLabel
from bill_lens.db import repository
from bill_lens.db.models import Bill, ExtractionRun
from bill_lens.extraction import FakeExtractor, ScriptedResponse
from bill_lens.extraction.openai_adapter import OpenAIConfigurationError
from bill_lens.pdf_text import extract_pdf_text
from bill_lens.validation import derive_flags, derive_status
from tests.helpers import ROOT

pytestmark = pytest.mark.db


def pdf(case="bill_001"):
    return (ROOT / "dataset" / case / "bill.pdf").read_bytes()


def failed(data, code="rate_limited"):
    return FakeExtractor({sha256(data).hexdigest(): ScriptedResponse(
        "original evidence", error_code=code, input_tokens=3, output_tokens=4, latency_ms=5)})


def post(client, data=None):
    return client.post("/bills", files={"file": ("bill.pdf", pdf() if data is None else data, "application/pdf")})


@pytest.fixture
def api(db_engine, tmp_path):
    app = create_app(engine=db_engine, storage_root=tmp_path,
                     extractor=FakeExtractor.from_dataset(ROOT / "dataset"))
    with TestClient(app, raise_server_exceptions=False) as client:
        yield app, client


@pytest.mark.parametrize("code", ["rate_limited", "timeout", "provider_error"])
@pytest.mark.parametrize("case", ["bill_001", "bill_002"])
def test_retry_recovers_and_preserves_history(code, case, api, db_engine, tmp_path):
    app, client = api
    data = pdf(case)
    calls = []
    class Recovering:
        def extract(self, document):
            assert db_engine.pool.checkedout() == 0
            calls.append(document.file_sha256)
            adapter = failed(data, code) if len(calls) == 1 else app.state.extractor
            return adapter.extract(document)
    app.dependency_overrides[get_extractor] = lambda: Recovering()
    original = post(client, data)
    assert original.status_code == 201 and original.json()["status"] == "failed"
    before_files = {p: p.read_bytes() for p in tmp_path.rglob("*.pdf")}
    retry = post(client, data)
    body = retry.json()
    assert retry.status_code == 200 and body["id"] == original.json()["id"]
    assert body["status"] == ("processed" if case == "bill_001" else "needs_review")
    assert body["run"]["id"] != original.json()["run"]["id"]
    assert body["created_at"] == original.json()["created_at"]
    assert body["updated_at"] > original.json()["updated_at"]
    assert client.get(retry.headers["Location"]).json() == body
    assert post(client, data).json() == body and len(calls) == 2
    with Session(db_engine) as session:
        bill = session.scalars(select(Bill)).one()
        runs = session.scalars(select(ExtractionRun).order_by(ExtractionRun.created_at)).all()
        assert len(runs) == 2 and bill.processing_status == body["status"]
        assert runs[0].error_code == code and runs[0].raw_response == "original evidence"
        assert (runs[0].input_tokens, runs[0].output_tokens, runs[0].latency_ms) == (3, 4, 5)
        assert runs[0].created_at < runs[1].created_at
    assert {p: p.read_bytes() for p in tmp_path.rglob("*.pdf")} == before_files
    assert not list(tmp_path.rglob("*.tmp"))


@pytest.mark.parametrize("code", ["invalid_output", "refused", "truncated"])
def test_non_retryable_failure_does_not_call_extractor(code, api, db_engine):
    app, client = api
    app.dependency_overrides[get_extractor] = lambda: failed(pdf(), code)
    original = post(client).json()
    class Forbidden:
        def extract(self, document):
            pytest.fail("non-retryable failure must reuse the saved run")
    app.dependency_overrides[get_extractor] = lambda: Forbidden()
    result = post(client)
    assert result.status_code == 200 and result.json() == original
    with Session(db_engine) as session:
        assert session.scalars(select(ExtractionRun)).one()


def test_repeated_failures_append_and_remain_retryable(api, db_engine, tmp_path):
    app, client = api
    bodies = []
    for code in ("rate_limited", "timeout", "provider_error"):
        app.dependency_overrides[get_extractor] = lambda code=code: failed(pdf(), code)
        result = post(client)
        assert result.status_code == (201 if not bodies else 200)
        bodies.append(result.json())
        assert bodies[-1]["run"]["error_code"] == code
        assert client.get(result.headers["Location"]).json() == bodies[-1]
    assert len({body["run"]["id"] for body in bodies}) == 3
    assert bodies[0]["updated_at"] < bodies[1]["updated_at"] < bodies[2]["updated_at"]
    with Session(db_engine) as session:
        assert len(session.scalars(select(ExtractionRun)).all()) == 3
        assert session.scalars(select(Bill)).one().processing_status == "failed"
    assert len(list(tmp_path.rglob("*.pdf"))) == 1


@pytest.mark.parametrize("first,second", [
    ("processed", "failed"), ("needs_review", "failed"),
    ("failed", "processed"), ("failed", "failed"), ("processed", "needs_review"),
])
def test_concurrent_retries_record_both_and_never_downgrade(first, second, api, db_engine, tmp_path):
    app, client = api
    app.dependency_overrides[get_extractor] = lambda: failed(pdf())
    original = post(client).json()
    entered, releases, counter_lock = Barrier(3, timeout=10), [Event(), Event()], Lock()
    calls = []
    outcomes = []
    for status in (first, second):
        # A valid output with missing current total is needs_review for the same PDF.
        case = "bill_002" if status == "needs_review" else "bill_001"
        if status == "failed":
            outcomes.append(ScriptedResponse("later failure", error_code="timeout"))
        else:
            label = ExpectedLabel.model_validate_json((ROOT / "dataset" / case / "expected.json").read_text())
            outcomes.append(ScriptedResponse(label.fields.model_dump_json()))

    class Blocking:
        def extract(self, document):
            with counter_lock:
                index = len(calls)
                calls.append(document.file_sha256)
            entered.wait()
            assert releases[index].wait(10)
            return FakeExtractor({document.file_sha256: outcomes[index]}).extract(document)
    app.dependency_overrides[get_extractor] = lambda: Blocking()
    with ThreadPoolExecutor(2) as pool:
        futures = [pool.submit(post, client) for _ in range(2)]
        try:
            entered.wait()
            assert db_engine.pool.checkedout() == 0
            releases[0].set()
            done, pending = wait(futures, timeout=10, return_when=FIRST_COMPLETED)
            assert len(done) == 1
            first_response = done.pop().result()
            assert first_response.status_code == 200
            assert first_response.json()["status"] == first
            assert client.get(f"/bills/{original['id']}").json() == first_response.json()
            releases[1].set()
            second_response = pending.pop().result(timeout=10)
        finally:
            for release in releases:
                release.set()
    expected = first if second == "failed" and first != "failed" else second
    assert second_response.status_code == 200 and second_response.json()["status"] == expected
    assert client.get(f"/bills/{original['id']}").json() == second_response.json()
    with Session(db_engine) as session:
        runs = session.scalars(select(ExtractionRun).order_by(ExtractionRun.created_at)).all()
        assert [run.status for run in runs] == ["failed", first, second]
        assert session.scalars(select(Bill)).one().processing_status == expected
        chosen = runs[1] if second == "failed" and first != "failed" else runs[2]
        assert str(chosen.id) == second_response.json()["run"]["id"]
        assert len({run.created_at for run in runs}) == 3
    assert len(calls) == 2 and len(list(tmp_path.rglob("*.pdf"))) == 1
    assert not list(tmp_path.rglob("*.tmp"))


@pytest.mark.parametrize("failure", ["extractor", "configuration", "append", "commit"])
def test_failed_retry_transaction_leaves_history_and_file_untouched(failure, api, db_engine, tmp_path, monkeypatch):
    app, client = api
    app.dependency_overrides[get_extractor] = lambda: failed(pdf())
    original = post(client).json()
    files = {p: p.read_bytes() for p in tmp_path.rglob("*.pdf")}
    app.dependency_overrides.clear()
    def fail(*args, **kwargs):
        raise RuntimeError("PRIVATE")
    with monkeypatch.context() as patch:
        if failure in {"extractor", "configuration"}:
            def broken(document):
                if failure == "configuration":
                    raise OpenAIConfigurationError("authentication")
                fail()
            patch.setattr(app.state.extractor, "extract", broken)
        elif failure == "append":
            original_append = service.append_extraction_run
            def broken_append(*args, **kwargs):
                original_append(*args, **kwargs)
                fail()
            patch.setattr(service, "append_extraction_run", broken_append)
        else:
            def before_commit(session):
                if not session.in_nested_transaction():
                    fail()
            event.listen(Session, "before_commit", before_commit)
        try:
            result = post(client)
            assert result.status_code == 500 and result.json() == {"error": "internal_error"}
        finally:
            if failure == "commit":
                event.remove(Session, "before_commit", before_commit)
    assert client.get(f"/bills/{original['id']}").json() == original
    with Session(db_engine) as session:
        assert session.scalars(select(ExtractionRun)).one()
        assert session.scalars(select(Bill)).one().processing_status == "failed"
    assert {p: p.read_bytes() for p in tmp_path.rglob("*.pdf")} == files
    assert post(client).json()["status"] == "processed"


def test_retry_after_lost_commit_ack_reuses_committed_success(api, db_engine):
    app, client = api
    app.dependency_overrides[get_extractor] = lambda: failed(pdf())
    post(client)
    app.dependency_overrides.clear()
    def lost_ack(session):
        if not session.in_nested_transaction():
            raise RuntimeError("ack lost")
    event.listen(Session, "after_commit", lost_ack)
    try:
        assert post(client).status_code == 500
    finally:
        event.remove(Session, "after_commit", lost_ack)
    class Forbidden:
        def extract(self, document):
            pytest.fail("committed success must not be retried")
    app.dependency_overrides[get_extractor] = lambda: Forbidden()
    assert post(client).json()["status"] == "processed"
    with Session(db_engine) as session:
        assert len(session.scalars(select(ExtractionRun)).all()) == 2


def test_three_distinct_retries_do_not_hold_small_pool_connections(db_engine, tmp_path):
    with db_engine.connect() as connection:
        schema = connection.scalar(text("SELECT current_schema()"))
    engine = create_engine(db_engine.url, pool_size=2, max_overflow=0, pool_timeout=1,
                           connect_args={"options": f"-csearch_path={schema} -cstatement_timeout=10000 -clock_timeout=5000"})
    data = [pdf(f"bill_{i:03}") for i in range(1, 4)]
    initial = FakeExtractor({sha256(p).hexdigest(): ScriptedResponse(None, error_code="timeout") for p in data})
    app = create_app(engine=engine, storage_root=tmp_path, extractor=initial)
    entered, release = Barrier(4, timeout=10), Event()
    healthy = FakeExtractor.from_dataset(ROOT / "dataset")
    class Blocking:
        def extract(self, document):
            entered.wait()
            assert release.wait(10)
            return healthy.extract(document)
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            ids = [post(client, p).json()["id"] for p in data]
            app.dependency_overrides[get_extractor] = lambda: Blocking()
            with ThreadPoolExecutor(3) as pool:
                futures = [pool.submit(post, client, p) for p in data]
                try:
                    entered.wait()
                    assert engine.pool.checkedout() == 0
                    assert client.get(f"/bills/{ids[0]}").status_code == 200
                finally:
                    release.set()
                responses = [f.result(timeout=10) for f in futures]
            assert all(r.status_code == 200 and r.json()["status"] != "failed" for r in responses)
            assert {r.json()["id"] for r in responses} == set(ids)
        with Session(engine) as session:
            assert len(session.scalars(select(Bill)).all()) == 3
            assert len(session.scalars(select(ExtractionRun)).all()) == 6
        assert len(list(tmp_path.rglob("*.pdf"))) == 3
    finally:
        engine.dispose()


def test_append_time_advances_past_existing_timestamp(api, db_engine):
    app, client = api
    app.dependency_overrides[get_extractor] = lambda: failed(pdf())
    post(client)
    # Simulates a backwards clock correction / existing future timestamp. A
    # transaction-start now() or plain clock_timestamp() cannot order this append.
    with db_engine.begin() as connection:
        connection.execute(text("UPDATE extraction_runs SET created_at = '2100-01-01T00:00:00Z'"))
    app.dependency_overrides[get_extractor] = lambda: failed(pdf(), "timeout")
    result = post(client)
    assert result.status_code == 200 and result.json()["run"]["error_code"] == "timeout"
    with Session(db_engine) as session:
        runs = session.scalars(select(ExtractionRun).order_by(ExtractionRun.created_at)).all()
        assert (runs[1].created_at - runs[0].created_at).total_seconds() == 0.000001


def test_simultaneous_retry_appends_serialize_status_updates(api, db_engine, tmp_path):
    app, client = api
    app.dependency_overrides[get_extractor] = lambda: failed(pdf())
    original = post(client).json()
    barrier, lock, calls = Barrier(2, timeout=10), Lock(), []
    healthy = app.state.extractor
    class Racing:
        def extract(self, document):
            with lock:
                index = len(calls)
                calls.append(index)
            attempt = (healthy if index == 0 else failed(pdf(), "timeout")).extract(document)
            barrier.wait()  # Both enter append transactions together.
            return attempt
    app.dependency_overrides[get_extractor] = lambda: Racing()
    with ThreadPoolExecutor(2) as pool:
        futures = [pool.submit(post, client) for _ in range(2)]
        responses = [future.result(timeout=10) for future in futures]
    assert all(response.status_code == 200 for response in responses)
    current = client.get(f"/bills/{original['id']}").json()
    assert current["status"] == "processed"
    with Session(db_engine) as session:
        assert session.scalars(select(Bill)).one().processing_status == "processed"
        runs = session.scalars(select(ExtractionRun)).all()
        assert len(runs) == 3 and sum(run.error_code is None for run in runs) == 1
    assert len(calls) == 2 and len(list(tmp_path.rglob("*.pdf"))) == 1


def test_row_lock_blocks_success_until_failed_status_update_commits(api, db_engine, monkeypatch):
    app, client = api
    app.dependency_overrides[get_extractor] = lambda: failed(pdf())
    original = post(client).json()
    bill_id = UUID(original["id"])
    document = extract_pdf_text(pdf())
    failure = failed(pdf(), "timeout").extract(document)
    success = app.state.extractor.extract(document)
    paused, release, success_started = Event(), Event(), Event()
    role, backend_pids = local(), {}
    real_update = repository.update

    def pause_failed_update(*args, **kwargs):
        # This call is AFTER current_run_statement was evaluated but BEFORE the
        # Bill UPDATE. Without the row lock, its selected status can go stale.
        if getattr(role, "name", None) == "failure":
            paused.set()
            assert release.wait(15), "test did not release the failed append"
        return real_update(*args, **kwargs)

    monkeypatch.setattr(repository, "update", pause_failed_update)

    def append(name, attempt):
        role.name = name
        flags = derive_flags(attempt.fields) if attempt.fields else set()
        with Session(db_engine) as session, session.begin():
            backend_pids[name] = session.scalar(text("SELECT pg_backend_pid()"))
            if name == "success":
                success_started.set()
            repository.append_extraction_run(
                session, bill_id=bill_id, attempt=attempt, flags=flags,
                status=derive_status(flags) if attempt.fields else "failed",
            )

    with ThreadPoolExecutor(2) as pool:
        failed_future = pool.submit(append, "failure", failure)
        try:
            assert paused.wait(5), "failed append never reached the pre-UPDATE gate"
            success_future = pool.submit(append, "success", success)
            assert success_started.wait(5), "successful append never reached PostgreSQL"
            blocked = False
            deadline = monotonic() + 4
            with db_engine.connect() as observer:
                while not success_future.done():
                    blocked = observer.scalar(text(
                        "SELECT :holder = ANY(pg_blocking_pids(:waiter))"
                    ), {"holder": backend_pids["failure"], "waiter": backend_pids["success"]})
                    if blocked or monotonic() >= deadline:
                        break
                    # Bounded polling, not a fixed sleep used to infer blocking.
                    release.wait(0.01)
            finished_while_paused = success_future.done()
        finally:
            release.set()  # Always unblock workers, including assertion failures.
        failed_future.result(timeout=10)
        success_future.result(timeout=10)

    with Session(db_engine) as session:
        bill = session.get(Bill, bill_id)
        current = session.scalars(repository.current_run_statement(bill_id)).one()
        observed = (blocked, finished_while_paused, bill.processing_status, current.status)
        assert observed == (True, False, "processed", "processed"), (
            "expected success to wait for failure's lock and leave consistent status; "
            f"got (blocked, finished_while_paused, bill_status, current_status)={observed}"
        )
        runs = session.scalars(select(ExtractionRun).where(ExtractionRun.bill_id == bill_id)).all()
        assert len(runs) == 3 and sum(run.error_code is None for run in runs) == 1
        assert client.get(f"/bills/{bill_id}").json()["run"]["id"] == str(current.id)


@pytest.mark.parametrize("initial_status", [429, 401])
def test_configured_openai_upload_recovers_using_mock_transport(initial_status, db_engine, tmp_path, monkeypatch):
    from bill_lens.extraction import openai_adapter as module
    calls, clients = [], []
    raw = json.dumps(json.loads((ROOT / "dataset/bill_001/expected.json").read_text())["fields"])
    def handle(request):
        calls.append(json.loads(request.content))
        if len(calls) == 1:
            return httpx2.Response(initial_status, json={"error": {"message": "PRIVATE", "code": "test_error"}})
        return httpx2.Response(200, json={
            "id": "resp_test", "object": "response", "created_at": 0, "model": "resolved-model",
            "status": "completed", "error": None,
            "usage": {"input_tokens": 10, "output_tokens": 20, "total_tokens": 30},
            "output": [{"id": "msg_test", "type": "message", "role": "assistant", "status": "completed",
                        "content": [{"type": "output_text", "text": raw, "annotations": []}]}],
        })
    def factory(**kwargs):
        client = OpenAI(**kwargs, http_client=httpx2.Client(transport=httpx2.MockTransport(handle)))
        clients.append(client)
        return client
    monkeypatch.setattr(module, "OpenAI", factory)
    monkeypatch.setenv("BILL_EXTRACTOR", "openai")
    monkeypatch.setenv("OPENAI_MODEL", "test-model")
    monkeypatch.setenv("OPENAI_API_KEY", "test-only-key")
    with TestClient(create_app(engine=db_engine, storage_root=tmp_path), raise_server_exceptions=False) as client:
        first = post(client)
        assert first.status_code == (201 if initial_status == 429 else 500)
        if initial_status == 401:
            assert first.json() == {"error": "internal_error"}
            with Session(db_engine) as session:
                assert session.scalar(select(Bill)) is None and session.scalar(select(ExtractionRun)) is None
            assert not list(tmp_path.rglob("*.pdf"))
        second = post(client)
        assert second.status_code == (200 if initial_status == 429 else 201)
        body = second.json()
        assert body["status"] == "processed" and body["run"]["provider"] == "openai"
        assert body["run"]["model"] == "resolved-model" and body["run"]["prompt_version"] == "extract-v2"
        assert client.get(second.headers["Location"]).json() == body
        assert post(client).json() == body and len(calls) == 2
    assert clients[0].is_closed()
    with Session(db_engine) as session:
        assert session.scalars(select(Bill)).one().processing_status == "processed"
        assert len(session.scalars(select(ExtractionRun)).all()) == (2 if initial_status == 429 else 1)
    assert len(list(tmp_path.rglob("*.pdf"))) == 1
