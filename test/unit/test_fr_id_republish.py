"""The functional-id re-publish: which farmers it picks, the ids it uses, how it hooks into celery.

Runs without the platform: the selection query runs on SQLite with the columns it reads, the
templates render with Jinja the way the registry renders them, and celery apps are stand-ins.
"""

import importlib.util
import json
import sqlite3
import sys
import types
from pathlib import Path

from jinja2 import ChainableUndefined, Environment

ROOT = Path(__file__).resolve().parents[2]
EXTENSION = ROOT / "farmer-extension/src/openg2p_registry_farmer_extension"
TEMPLATES = EXTENSION / "templates"


def _load():
    spec = importlib.util.spec_from_file_location("fr_id_republish", EXTENSION / "fr_id_republish.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


republish = _load()
REGISTER = republish.FARMER_REGISTER_ID


def _db():
    db = sqlite3.connect(":memory:")
    db.executescript("""
        CREATE TABLE g2p_register_farmers (internal_record_id TEXT PRIMARY KEY, functional_record_id TEXT);
        CREATE TABLE outgoing_raw_data_payloads (payload_id TEXT PRIMARY KEY, raw_data_json TEXT);
        CREATE TABLE outgoing_raw_data (outgest_id TEXT PRIMARY KEY, payload_id TEXT, register_id TEXT,
                                        internal_record_id TEXT);
    """)
    return db


def _farmer(db, irid, fid):
    db.execute("INSERT INTO g2p_register_farmers VALUES (?, ?)", (irid, fid))


def _snapshot(db, payload, irid, fid, register=REGISTER):
    db.execute("INSERT INTO outgoing_raw_data_payloads VALUES (?, ?)",
               (payload, json.dumps({"internal_record_id": irid, "functional_record_id": fid})))
    for topic in ("a", "b"):  # one outgoing row per active topic, as the platform writes them
        db.execute("INSERT INTO outgoing_raw_data VALUES (?, ?, ?, ?)", (f"{payload}:{topic}", payload, register, irid))


def _pending(db, limit=republish.BATCH_SIZE):
    # SQLite takes the same :name binds as SQLAlchemy's text().
    return [row[0] for row in db.execute(republish.PENDING_SQL, republish.pending_params(limit))]


def test_picks_a_farmer_whose_only_notice_carried_the_placeholder():
    db = _db()
    _farmer(db, "f-1", "FR-000000000001")
    _snapshot(db, f"intake-1:{REGISTER}:f-1", "f-1", "TEMP-abc")
    assert _pending(db) == ["f-1"]


def test_skips_a_farmer_already_sent_with_its_functional_id():
    db = _db()
    _farmer(db, "f-1", "FR-000000000001")
    _snapshot(db, f"intake-1:{REGISTER}:f-1", "f-1", "TEMP-abc")
    _snapshot(db, f"cr-1:{REGISTER}:f-1", "f-1", "FR-000000000001")
    assert _pending(db) == []


def test_skips_a_farmer_still_waiting_for_its_functional_id():
    db = _db()
    _farmer(db, "f-1", "TEMP-abc")
    _snapshot(db, f"intake-1:{REGISTER}:f-1", "f-1", "TEMP-abc")
    assert _pending(db) == []


def test_republishes_a_farmer_once():
    db = _db()
    _farmer(db, "f-1", "FR-000000000001")
    _snapshot(db, f"intake-1:{REGISTER}:f-1", "f-1", "TEMP-abc")
    # The re-publish payload exists, its transformation has not filled the snapshot in yet.
    db.execute("INSERT INTO outgoing_raw_data_payloads VALUES (?, ?)", (republish.payload_id("f-1"), "{}"))
    assert _pending(db) == []


def test_ignores_other_registers_and_farmers_never_published():
    db = _db()
    _farmer(db, "f-1", "FR-000000000001")
    _farmer(db, "f-2", "FR-000000000002")
    _snapshot(db, "intake-1:other-register:f-1", "f-1", "TEMP-abc", register="other-register")
    assert _pending(db) == []


def test_batch_is_limited():
    db = _db()
    for n in range(3):
        _farmer(db, f"f-{n}", f"FR-00000000000{n}")
        _snapshot(db, f"intake-{n}:{REGISTER}:f-{n}", f"f-{n}", f"TEMP-{n}")
    assert _pending(db, limit=2) == ["f-0", "f-1"]


def test_republish_payload_id_never_collides_with_the_intake_one():
    intake_payload = f"9f1c2e4a-0000-4000-8000-000000000000:{REGISTER}:f-1"
    assert republish.payload_id("f-1") != intake_payload
    assert republish.payload_id("f-1") == f"republish-fr-id:f-1:{REGISTER}:f-1"
    assert republish.payload_id("f-1") != republish.payload_id("f-2")


def _notice(template_name, functional_id):
    env = Environment(undefined=ChainableUndefined)
    template = env.from_string((TEMPLATES / template_name).read_text(encoding="utf-8"))
    farmer = {"internal_record_id": "069999d6-c45a-4360-af58-a119e09fb84a", "functional_record_id": functional_id,
              "foundational_id": "1234567890123456", "last_approved_at": "2026-11-11 07:07:57.887356"}
    return json.loads(template.render(expanded=farmer))


def test_placeholder_and_functional_id_notices_have_different_event_ids():
    for name in ("farmer_registry_farmer_profile_changed_v1.j2", "farmer_reference_changed_v1.j2"):
        first, again = _notice(name, "TEMP-0f3a"), _notice(name, "FR-329598534196")
        assert first["event_id"] != again["event_id"], name
        assert again["event_id"].endswith(":FR-329598534196"), name
        assert 0 < len(again["event_id"]) <= 256, name  # the receivers' validation_schema bound


def test_beat_schedule_keeps_the_native_entries_and_targets_the_worker_queue():
    native = {"outgest_data_publish_beat_producer": {"task": "outgest_data_publish_beat_producer", "schedule": 20}}
    app = types.SimpleNamespace(conf=types.SimpleNamespace(beat_schedule=dict(native)))
    republish.add_schedule(app, "registry_worker_queue")
    republish.add_schedule(app, "registry_worker_queue")
    assert {k: v for k, v in app.conf.beat_schedule.items() if k in native} == native
    assert app.conf.beat_schedule[republish.SCHEDULE_KEY] == {
        "task": republish.TASK_NAME, "schedule": republish.SCHEDULE_SECONDS,
        "options": {"queue": "registry_worker_queue"}}
    assert len(app.conf.beat_schedule) == 2


def test_install_registers_the_task_once_in_the_worker(monkeypatch):
    registered = []

    class App:
        def task(self, name):
            def decorate(fn):
                registered.append(name)
                return fn
            return decorate

    engine = types.ModuleType("openg2p_registry_celery_worker.engine")
    engine.Engine = types.SimpleNamespace(construct_async_db_datasource=lambda: "postgresql+asyncpg://x")
    monkeypatch.setitem(sys.modules, "openg2p_registry_celery_worker", types.ModuleType("openg2p_registry_celery_worker"))
    monkeypatch.setitem(sys.modules, "openg2p_registry_celery_worker.engine", engine)
    monkeypatch.setitem(sys.modules, "openg2p_registry_celery_worker.app", types.SimpleNamespace(celery_app=App()))
    monkeypatch.delitem(sys.modules, "openg2p_registry_celery_beat.app", raising=False)
    module = _load()
    for _ in range(3):
        module.install()
    assert registered == [module.TASK_NAME]


def test_install_does_nothing_outside_celery(monkeypatch):
    monkeypatch.delitem(sys.modules, "openg2p_registry_celery_worker.app", raising=False)
    monkeypatch.delitem(sys.modules, "openg2p_registry_celery_beat.app", raising=False)
    _load().install()
