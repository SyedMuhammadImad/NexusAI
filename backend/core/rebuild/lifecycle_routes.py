"""Authenticated research persistence; approvals are not an HTTP input."""
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict

from .lifecycle_contracts import ExecutionRequest, Identity, SourceEvent, TradeIntent


class ValidateSource(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_event_id: Identity


class EvaluateIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    safety_decision_id: Identity


def lifecycle_router(access):
    router = APIRouter(prefix="/api/core/lifecycle", dependencies=[Depends(access)])

    def call(method, *args):
        try:
            return {"record": method(*args), "execution_enabled": False, "scope": "NON_EXECUTING"}
        except KeyError as exc:
            raise HTTPException(404, "Lifecycle record not found") from exc
        except (ValueError, sqlite3.IntegrityError) as exc:
            raise HTTPException(409, str(exc)) from exc

    @router.post("/sources")
    def source(event: SourceEvent, request: Request):
        return call(request.app.state.lifecycle.save_source, event)

    @router.post("/signals")
    def signal(body: ValidateSource, request: Request):
        return call(request.app.state.lifecycle.validate_source, body.source_event_id)

    @router.post("/intents")
    def intent(body: TradeIntent, request: Request):
        return call(request.app.state.lifecycle.create_intent, body)

    @router.post("/intents/{intent_id}/evaluate")
    def evaluate(intent_id: str, body: EvaluateIntent, request: Request):
        if request.app.state.safety is not None:
            provider = request.app.state.safety_input_provider
            try:
                inputs = provider(intent_id) if provider else None
            except Exception:
                inputs = None
            return call(request.app.state.safety.evaluate, intent_id, body.safety_decision_id,
                        inputs)
        return call(request.app.state.lifecycle.reject_intent, intent_id, body.safety_decision_id)

    @router.post("/requests")
    def execution_request(body: ExecutionRequest, request: Request):
        if request.app.state.safety is not None:
            return call(request.app.state.safety.eligible_request, body.intent_id, body.safety_decision_id, body.execution_request_id)
        return call(request.app.state.lifecycle.create_execution_request, body)

    @router.get("/sources/{source_event_id}/trace")
    def trace(source_event_id: str, request: Request):
        return call(request.app.state.lifecycle.trace, source_event_id)

    def execution(request):
        engine = request.app.state.execution
        if engine is None:
            raise HTTPException(423, 'P3 execution is not configured; default app remains disabled')
        return engine

    @router.post('/requests/{execution_request_id}/submit')
    def submit(execution_request_id: Identity, request: Request):
        # Factory permits only synthetic FIXTURE adapters, never native MT5 here.
        result = call(execution(request).submit, execution_request_id)
        return {**result, 'scope':'P3_FIXTURE_ONLY'}

    @router.post('/reconcile')
    def reconcile(request: Request):
        result = call(execution(request).reconcile)
        return {**result, 'scope':'P3_FIXTURE_ONLY'}

    return router
