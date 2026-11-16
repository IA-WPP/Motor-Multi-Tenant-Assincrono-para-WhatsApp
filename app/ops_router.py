"""Extensão aditiva, somente leitura, para o motor no commit documentado.

Copie para app/ops_router.py. Não usa ADMIN_API_KEY nem altera rotas existentes.
"""
import asyncio
import hashlib
import hmac
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import AuditLog, Company, CustomerSession, MessageHistory, OrderRecord

logger = logging.getLogger("motor.ops.access")
basic = HTTPBasic(auto_error=False)
QUEUES = ("queue:webhooks:pending", "queue:webhooks:processing", "queue:webhooks:dlq")
STALE_SECONDS = 300


@dataclass(frozen=True)
class Principal:
    username: str
    tenant_ids: tuple[str, ...]
    global_access: bool


def verify_password(password: str, encoded: str) -> bool:
    try:
        if not isinstance(encoded, str):
            return False
        salt, expected = encoded.split("$")
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 600_000).hex()
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


async def operator(request: Request, response: Response, credentials: HTTPBasicCredentials | None = Depends(basic)) -> Principal:
    response.headers["Cache-Control"] = "no-store"
    if request.url.scheme != "https" and os.getenv("OPS_ALLOW_HTTP_LOCAL") != "true":
        raise HTTPException(400, "Console exige HTTPS. HTTP deve ser habilitado explicitamente apenas em desenvolvimento local.")
    try:
        users = json.loads(os.environ.get("OPS_USERS_JSON", "{}"))
        if not isinstance(users, dict) or not users:
            raise ValueError()
    except (ValueError, TypeError):
        raise HTTPException(503, "Operadores não configurados no servidor.") from None
    user = users.get(credentials.username) if credentials else None
    # Hash fictício mantém custo similar para usuário inexistente.
    encoded = user.get("password_hash", "") if isinstance(user, dict) else "00" * 16 + "$" + "00" * 32
    valid = await asyncio.to_thread(verify_password, credentials.password if credentials else "", encoded)
    if not credentials or not isinstance(user, dict) or not valid:
        logger.warning("ops_login_denied")
        raise HTTPException(401, "Credencial de operador inválida.")
    ids = user.get("tenant_ids", [])
    if not isinstance(ids, list) or not all(isinstance(i, str) for i in ids):
        raise HTTPException(503, "Escopo do operador inválido no servidor.")
    principal = Principal(credentials.username, tuple(ids), user.get("global_access") is True)
    # Sem telefones, senhas, headers ou payloads de mensagens no log de acesso.
    logger.info("ops_read operator=%s route=%s", principal.username, request.url.path)
    return principal


def scope_ids(principal: Principal, tenant_id: str | None) -> tuple[str, ...] | None:
    if tenant_id:
        if not principal.global_access and tenant_id not in principal.tenant_ids:
            raise HTTPException(403, "Tenant fora do escopo do operador.")
        return (tenant_id,)
    if not principal.global_access:
        raise HTTPException(403, "Selecione um tenant autorizado; visão global não permitida.")
    return None


def scoped(column, ids):
    return column.in_(ids) if ids is not None else True


def aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def iso(value: datetime | None) -> str | None:
    return aware(value).isoformat() if value else None


def period(start: datetime, end: datetime):
    if start.tzinfo is None or end.tzinfo is None:
        raise HTTPException(422, "Informe timezone no período.")
    start, end = aware(start), aware(end)
    if end <= start or end - start > timedelta(days=31):
        raise HTTPException(422, "Período deve ter entre 1 segundo e 31 dias.")
    return start, end


def mask(phone: str | None) -> str:
    return "•• •••••-" + phone[-4:] if phone else "Não disponível"


def instance(company: Company):
    settings = company.settings or {}
    last = settings.get("last_connection_update")
    fresh, observed = False, None
    try:
        observed_dt = aware(datetime.fromisoformat(last.replace("Z", "+00:00")))
        observed = iso(observed_dt)
        age = (datetime.now(timezone.utc) - observed_dt).total_seconds()
        fresh = 0 <= age <= STALE_SECONDS
    except (ValueError, AttributeError, TypeError):
        pass
    state = settings.get("connection_status")
    normalized = {"open": "connected", "close": "disconnected", "refused": "disconnected", "disconnected": "disconnected", "connecting": "reconnecting"}.get(state, "unknown")
    return {"id": company.id, "tenantId": company.id, "name": company.instance_name,
            "status": normalized if fresh else "unknown", "observedAt": observed, "phone": mask(company.phone_number)}


def create_ops_router(get_redis_client):
    router = APIRouter(prefix="/ops-api/v1", tags=["Operations Console"])

    @router.get("/session")
    async def session(p: Principal = Depends(operator), db: AsyncSession = Depends(get_db)):
        companies = (await db.execute(select(Company).where(scoped(Company.id, None if p.global_access else p.tenant_ids)).order_by(Company.name))).scalars().all()
        return {"operator": {"name": p.username, "role": "Administrador global" if p.global_access else "Operador por tenant"},
                "canViewGlobal": p.global_access, "tenants": [{"id": c.id, "name": c.name} for c in companies]}

    @router.get("/instances")
    async def instances(tenantId: str | None = None, p: Principal = Depends(operator), db: AsyncSession = Depends(get_db)):
        ids = scope_ids(p, tenantId)
        rows = (await db.execute(select(Company).where(scoped(Company.id, ids), Company.active.is_(True)).order_by(Company.name))).scalars().all()
        return [instance(c) for c in rows]

    @router.get("/conversations")
    async def conversations(from_: datetime = Query(alias="from"), to: datetime = Query(), tenantId: str | None = None,
                            search: str = Query(default="", max_length=100), status: Literal["", "active", "handoff"] = "",
                            cursor: int = Query(default=0, ge=0, le=100_000), p: Principal = Depends(operator), db: AsyncSession = Depends(get_db)):
        ids = scope_ids(p, tenantId)
        start, end = period(from_, to)
        handoff = CustomerSession.session_data["human_handoff"].as_boolean()
        stmt = select(CustomerSession, Company).join(Company, CustomerSession.company_id == Company.id).where(
            scoped(CustomerSession.company_id, ids), CustomerSession.last_interaction >= start, CustomerSession.last_interaction < end)
        if search:
            # contains(autoescape) impede que % e _ ampliem a busca involuntariamente.
            stmt = stmt.where(or_(func.lower(CustomerSession.customer_name).contains(search.lower(), autoescape=True), CustomerSession.phone_number.contains(search, autoescape=True)))
        if status == "handoff":
            stmt = stmt.where(handoff.is_(True))
        elif status == "active":
            stmt = stmt.where(or_(handoff.is_(False), handoff.is_(None)))
        rows = (await db.execute(stmt.order_by(CustomerSession.last_interaction.desc(), CustomerSession.id).offset(cursor).limit(7))).all()
        items = []
        for s, company in rows[:6]:
            # Isolamento obrigatório em cada lookup: telefone não é identidade global.
            messages = (await db.execute(select(MessageHistory).where(MessageHistory.company_id == s.company_id, MessageHistory.customer_phone == s.phone_number).order_by(MessageHistory.created_at.desc(), MessageHistory.id.desc()).limit(200))).scalars().all()
            data = s.session_data or {}
            items.append({"id": s.id, "tenantId": s.company_id, "customer": s.customer_name or "Cliente", "phone": mask(s.phone_number),
                          "preview": messages[0].content if messages else "Sem histórico persistido", "updatedAt": iso(s.last_interaction),
                          "status": "handoff" if data.get("human_handoff") else "active", "unread": None, "instance": company.instance_name,
                          "sessionId": s.id, "graphState": s.current_step, "orderId": data.get("order_id"),
                          "messages": [{"id": m.id, "role": "customer" if m.role == "user" else "ai", "text": m.content, "at": iso(m.created_at), "delivery": "unknown"} for m in reversed(messages)]})
        return {"items": items, "nextCursor": str(cursor + 6) if len(rows) > 6 else None}

    @router.get("/events")
    async def events(from_: datetime = Query(alias="from"), to: datetime = Query(), tenantId: str | None = None,
                     p: Principal = Depends(operator), db: AsyncSession = Depends(get_db)):
        ids = scope_ids(p, tenantId)
        start, end = period(from_, to)
        rows = (await db.execute(select(AuditLog).where(scoped(AuditLog.company_id, ids), AuditLog.created_at >= start, AuditLog.created_at < end).order_by(AuditLog.created_at.desc(), AuditLog.id).limit(200))).scalars().all()
        keys = {(r.company_id, r.phone_number) for r in rows if r.phone_number}
        sessions = []
        if keys:
            sessions = (await db.execute(select(CustomerSession).where(scoped(CustomerSession.company_id, ids), or_(*[and_(CustomerSession.company_id == cid, CustomerSession.phone_number == phone) for cid, phone in keys])).order_by(CustomerSession.last_interaction))).scalars().all()
        session_map = {(s.company_id, s.phone_number): s.id for s in sessions}
        summaries = {"message_processed": "Processamento registrado pelo motor", "WHATSAPP_SEND_FAILED": "Falha definitiva no envio WhatsApp", "WHATSAPP_DISCONNECTED_ALERT": "Instância WhatsApp desconectada", "WHATSAPP_CONNECTED": "Conexão WhatsApp restabelecida", "SECURITY_INPUT_RAIL_BLOCKED": "Entrada bloqueada pelo guardrail"}
        return [{"id": r.id, "tenantId": r.company_id, "conversationId": session_map.get((r.company_id, r.phone_number)),
                 "at": iso(r.created_at), "service": "audit_logs", "kind": r.event_type,
                 "severity": "error" if r.event_type in {"WHATSAPP_SEND_FAILED", "WHATSAPP_DISCONNECTED_ALERT"} else "warning" if "BLOCKED" in r.event_type else "info",
                 "summary": summaries.get(r.event_type, "Evento persistido na auditoria"), "code": r.event_type if "FAILED" in r.event_type else None} for r in rows]

    @router.get("/queues")
    async def queues(tenantId: str | None = None, p: Principal = Depends(operator)):
        scope_ids(p, tenantId)
        # Filas são compartilhadas, não há contagem segura por tenant no Redis atual.
        if tenantId or not p.global_access:
            return [{"key": k, "depth": None, "oldestAgeSeconds": None} for k in QUEUES]
        redis = get_redis_client()
        if redis is None:
            return [{"key": k, "depth": None, "oldestAgeSeconds": None} for k in QUEUES]
        try:
            depths = await asyncio.wait_for(asyncio.gather(*(redis.llen(k) for k in QUEUES)), timeout=3)
        except Exception:
            raise HTTPException(503, "Redis indisponível para consulta operacional.") from None
        return [{"key": k, "depth": n, "oldestAgeSeconds": None} for k, n in zip(QUEUES, depths)]

    @router.get("/orders")
    async def orders(from_: datetime = Query(alias="from"), to: datetime = Query(), tenantId: str | None = None,
                     p: Principal = Depends(operator), db: AsyncSession = Depends(get_db)):
        ids = scope_ids(p, tenantId)
        start, end = period(from_, to)
        rows = (await db.execute(select(OrderRecord).where(scoped(OrderRecord.company_id, ids), OrderRecord.created_at >= start, OrderRecord.created_at < end).order_by(OrderRecord.created_at.desc(), OrderRecord.id).limit(200))).scalars().all()
        return [{"id": r.id, "tenantId": r.company_id, "customer": r.customer_name or "Cliente", "phone": mask(r.customer_phone),
                 "status": r.status, "paymentMethod": r.payment_method, "at": iso(r.created_at),
                 "items": [{"name": str(i.get("descricao", "Item")), "quantity": float(i["quantidade"]) if isinstance(i.get("quantidade"), (int, float)) else None} for i in r.items if isinstance(i, dict)]} for r in rows]

    @router.get("/overview")
    async def overview(from_: datetime = Query(alias="from"), to: datetime = Query(), tenantId: str | None = None,
                       p: Principal = Depends(operator), db: AsyncSession = Depends(get_db)):
        ids = scope_ids(p, tenantId)
        start, end = period(from_, to)
        conditions = [scoped(AuditLog.company_id, ids), AuditLog.created_at >= start, AuditLog.created_at < end, AuditLog.event_type == "message_processed"]
        processed = (await db.execute(select(func.count()).select_from(AuditLog).where(*conditions))).scalar_one()
        handoff = CustomerSession.session_data["human_handoff"].as_boolean()
        session_conditions = [scoped(CustomerSession.company_id, ids), CustomerSession.last_interaction >= start, CustomerSession.last_interaction < end]
        handoffs = (await db.execute(select(func.count()).select_from(CustomerSession).where(*session_conditions, handoff.is_(True)))).scalar_one()
        active = (await db.execute(select(func.count()).select_from(CustomerSession).where(*session_conditions, or_(handoff.is_(False), handoff.is_(None))))).scalar_one()
        companies = (await db.execute(select(Company).where(scoped(Company.id, ids), Company.active.is_(True)))).scalars().all()
        connected = sum(instance(c)["status"] == "connected" for c in companies)
        step = (end - start) / 24
        buckets = [(start + i * step, start + (i + 1) * step) for i in range(24)]
        counts = (await db.execute(select(*[func.sum(case((and_(AuditLog.created_at >= a, AuditLog.created_at < b), 1), else_=0)) for a, b in buckets]).where(*conditions))).one()
        p50 = p95 = None
        if db.get_bind().dialect.name == "postgresql":
            p50, p95 = (await db.execute(select(func.percentile_cont(.5).within_group(AuditLog.execution_time_ms), func.percentile_cont(.95).within_group(AuditLog.execution_time_ms)).where(*conditions, AuditLog.execution_time_ms >= 0))).one()
        def metric(label, value, unit, definition):
            return {"label": label, "value": value, "unit": unit, "definition": definition}
        return {"from": iso(start), "to": iso(end), "metrics": [
            metric("Instâncias conectadas", connected, "instâncias", "Snapshot: connection_status=open com atualização há no máximo 5 minutos. Estado antigo é desconhecido."),
            metric("Conversas ativas", active, "conversas", "Sessões com interação no período e sem human_handoff. Não implica atividade neste instante."),
            metric("Mensagens processadas", processed, "mensagens", "Quantidade de registros audit_logs.event_type=message_processed no período. Não comprova entrega."),
            metric("Handoffs humanos", handoffs, "conversas", "Estado atual human_handoff=true em sessões com interação no período; não é quantidade de transições."),
            metric("Latência P50", p50, "ms", "Percentil 50 de execution_time_ms para message_processed no PostgreSQL. Mede processamento do motor, não espera na fila nem entrega ponta a ponta."),
            metric("Latência P95", p95, "ms", "Percentil 95 de execution_time_ms para message_processed no PostgreSQL. Não é tracing distribuído. Indisponível em SQLite."),
            metric("Sucesso no envio", None, "%", "Requer eventos persistidos de tentativa e confirmação de envio com denominador confiável."),
            metric("Workers ativos", None, "workers", "Requer heartbeat por worker. Comprimento da fila processing não representa workers."),
        ], "throughput": [{"at": iso(a), "count": int(n or 0), "p95": None} for (a, _), n in zip(buckets, counts)]}

    return router
