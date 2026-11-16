"""Executar com PYTHONPATH apontando para a raiz do motor e integration/."""
import hashlib
import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import get_db
from app.models import AuditLog, Base, Company, CustomerSession, MessageHistory, OrderRecord
from ops_router import create_ops_router, instance


@pytest_asyncio.fixture
async def client(monkeypatch):
    salt = bytes.fromhex("11" * 16)
    password = "test-password-only-1234"
    password_hash = salt.hex() + "$" + hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 600_000).hex()
    monkeypatch.setenv("OPS_USERS_JSON", json.dumps({
        "restricted": {"password_hash": password_hash, "tenant_ids": ["a"], "global_access": False},
        "admin": {"password_hash": password_hash, "tenant_ids": [], "global_access": True},
    }))
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(timezone.utc)
    async with factory() as db:
        db.add_all([Company(id=i, owner_id="owner", name=f"Tenant {i}", instance_name=f"wa-{i}", segment="test", settings={"connection_status": "open", "last_connection_update": now.isoformat()}) for i in ["a", "b"]])
        for i in ["a", "b"]:
            db.add(CustomerSession(id=f"s-{i}", company_id=i, phone_number="5592999994444", customer_name=f"Cliente {i}", current_step="pagamento", session_data={"human_handoff": i == "a"}, last_interaction=now))
            db.add(MessageHistory(id=f"m-{i}", company_id=i, customer_phone="5592999994444", role="user", content=f"privado-{i}", created_at=now))
            db.add(AuditLog(id=f"e-{i}", company_id=i, phone_number="5592999994444", event_type="message_processed", payload={"secret": "NEVER_RETURN"}, execution_time_ms=140, created_at=now))
            db.add(OrderRecord(id=f"o-{i}", company_id=i, customer_phone="5592999994444", customer_name=f"Cliente {i}", items=[{"descricao": f"Item {i}", "quantidade": 2}], status="recebido", created_at=now))
        await db.commit()
    async def db_override():
        async with factory() as db:
            yield db
    class Redis:
        async def llen(self, key):
            return 7
    app = FastAPI()
    app.include_router(create_ops_router(lambda: Redis()))
    app.dependency_overrides[get_db] = db_override
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://test") as c:
        c.auth = httpx.BasicAuth("restricted", password)
        c.period = {"from": (now - timedelta(hours=1)).isoformat(), "to": (now + timedelta(minutes=1)).isoformat()}
        c.password = password
        c.factory = factory
        yield c
    await engine.dispose()


@pytest.mark.asyncio
async def test_authentication_and_no_admin_key(client):
    assert (await client.get("/ops-api/v1/session", auth=None)).status_code == 401
    assert (await client.get("/ops-api/v1/session", auth=("restricted", "wrong"))).status_code == 401
    r = await client.get("/ops-api/v1/session")
    assert r.status_code == 200
    assert r.headers["cache-control"] == "no-store"
    assert r.json()["tenants"] == [{"id": "a", "name": "Tenant a"}]
    assert r.json()["canViewGlobal"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ["overview", "conversations", "events", "orders", "instances", "queues"])
async def test_scope_cannot_be_escalated(client, route):
    for tenant in [None, "b"]:
        params = dict(client.period)
        if tenant:
            params["tenantId"] = tenant
        assert (await client.get(f"/ops-api/v1/{route}", params=params)).status_code == 403


@pytest.mark.asyncio
async def test_same_phone_different_tenant_cannot_leak_messages(client):
    response = await client.get("/ops-api/v1/conversations", params={**client.period, "tenantId": "a"})
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 1
    assert data["items"][0]["messages"][0]["text"] == "privado-a"
    assert "privado-b" not in response.text
    assert "5592999994444" not in response.text
    assert data["items"][0]["unread"] is None
    assert data["items"][0]["messages"][0]["delivery"] == "unknown"


@pytest.mark.asyncio
async def test_filters_and_cursor_validation(client):
    params = {**client.period, "tenantId": "a"}
    assert (await client.get("/ops-api/v1/conversations", params={**params, "status": "active"})).json()["items"] == []
    assert len((await client.get("/ops-api/v1/conversations", params={**params, "status": "handoff"})).json()["items"]) == 1
    assert (await client.get("/ops-api/v1/conversations", params={**params, "search": "%"})).json()["items"] == []
    assert (await client.get("/ops-api/v1/conversations", params={**params, "cursor": -1})).status_code == 422


@pytest.mark.asyncio
async def test_metrics_use_real_counts_and_no_fabricated_latency(client):
    r = await client.get("/ops-api/v1/overview", params={**client.period, "tenantId": "a"})
    assert r.status_code == 200, r.text
    data = r.json()
    values = {m["label"]: m["value"] for m in data["metrics"]}
    assert values["Mensagens processadas"] == 1
    assert values["Handoffs humanos"] == 1
    assert values["Conversas ativas"] == 0
    assert values["Latência P95"] is None
    assert values["Workers ativos"] is None
    assert sum(x["count"] for x in data["throughput"]) == 1


@pytest.mark.asyncio
async def test_events_do_not_expose_payload(client):
    r = await client.get("/ops-api/v1/events", params={**client.period, "tenantId": "a"})
    assert r.status_code == 200
    assert r.json()[0]["conversationId"] == "s-a"
    assert "NEVER_RETURN" not in r.text
    assert '"tenantId":"b"' not in r.text


@pytest.mark.asyncio
async def test_queue_global_only_and_orders_masked(client):
    r = await client.get("/ops-api/v1/queues", params={"tenantId": "a"})
    assert all(q["depth"] is None for q in r.json())
    r = await client.get("/ops-api/v1/queues", auth=("admin", client.password))
    assert all(q["depth"] == 7 for q in r.json())
    orders = await client.get("/ops-api/v1/orders", params={**client.period, "tenantId": "a"})
    assert orders.json()[0]["items"][0] == {"name": "Item a", "quantity": 2.0}
    assert "5592999994444" not in orders.text


@pytest.mark.asyncio
async def test_invalid_period_rejected(client):
    params = {"tenantId": "a", "from": client.period["to"], "to": client.period["from"]}
    assert (await client.get("/ops-api/v1/overview", params=params)).status_code == 422


def test_stale_instance_is_unknown():
    c = Company(id="a", instance_name="wa-a", settings={"connection_status": "open", "last_connection_update": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()})
    assert instance(c)["status"] == "unknown"
    c.settings = {"connection_status": "open"}
    assert instance(c)["status"] == "unknown"


@pytest.mark.asyncio
async def test_pagination_preserves_scope(client):
    now = datetime.now(timezone.utc) - timedelta(minutes=1)
    async with client.factory() as db:
        db.add_all([CustomerSession(id=f"extra-{i}", company_id="a", phone_number=f"555000{i}", customer_name=f"Extra {i}", session_data={}, last_interaction=now) for i in range(7)])
        await db.commit()
    params = {**client.period, "tenantId": "a"}
    first = (await client.get("/ops-api/v1/conversations", params=params)).json()
    assert len(first["items"]) == 6
    assert first["nextCursor"] == "6"
    second = (await client.get("/ops-api/v1/conversations", params={**params, "cursor": first["nextCursor"]})).json()
    assert len(second["items"]) == 2
    assert second["nextCursor"] is None
    assert not ({c["id"] for c in first["items"]} & {c["id"] for c in second["items"]})
    assert all(c["tenantId"] == "a" for c in first["items"] + second["items"])


@pytest.mark.asyncio
async def test_https_required_and_missing_configuration_fails_closed(client, monkeypatch):
    assert (await client.get("http://test/ops-api/v1/session")).status_code == 400
    monkeypatch.delenv("OPS_USERS_JSON")
    assert (await client.get("/ops-api/v1/session")).status_code == 503
