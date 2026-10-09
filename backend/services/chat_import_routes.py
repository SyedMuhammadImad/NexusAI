"""Historical import endpoints, isolated from trading controls."""

import asyncio
import mimetypes

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from services.chat_import_service import ChatImportService, MAX_UPLOAD
from services.trader_learning_store import TraderLearningStore
from services.yahoo_history_service import YahooHistoryService
from services.trader_imitation_model import TraderImitationModelService


class Correction(BaseModel):
    entry_price: float = Field(gt=0, allow_inf_nan=False)
    stop_loss: float = Field(gt=0, allow_inf_nan=False)
    take_profit_1: float = Field(gt=0, allow_inf_nan=False)
    note: str = Field(min_length=5, max_length=1000)


def chat_import_router(access_dependency, service_factory=None):
    router = APIRouter(prefix="/api/private/chat-imports", dependencies=[Depends(access_dependency)])

    def service():
        if service_factory is not None:
            return service_factory()
        return ChatImportService(learning_store=TraderLearningStore())

    async def run(method, *args):
        try:
            return await asyncio.to_thread(method, *args)
        except KeyError as exc:
            raise HTTPException(404, "Import or message not found") from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @router.get("")
    async def list_imports():
        return {"imports": await run(service().list_imports), "execution_enabled": False}

    @router.post("")
    async def upload(file: UploadFile = File(...), date_order: str | None = Form(None),
                     utc_offset: int | None = Form(None), group: str = Form("REDACTED_SOURCE")):
        try:
            content = await file.read(MAX_UPLOAD + 1)
        finally:
            await file.close()
        if len(content) > MAX_UPLOAD:
            raise HTTPException(413, "Archive exceeds the 100 MB upload limit")
        return await run(service().import_file, content, file.filename or "", date_order, utc_offset, group)

    @router.get("/{import_id}/messages")
    async def messages(import_id: str, kind: str = "all", search: str = Query("", max_length=200),
                       offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=200)):
        return await run(service().messages, import_id, kind, search, offset, limit)

    @router.post("/{import_id}/yahoo-enrichment")
    async def enrich(import_id: str):
        return await run(YahooHistoryService(service()).enrich, import_id)

    @router.get("/{import_id}/yahoo-enrichment")
    async def enrichment_status(import_id: str):
        return await run(YahooHistoryService(service()).latest, import_id)

    @router.post("/{import_id}/train")
    async def train_import(import_id: str):
        raise HTTPException(423, "Training blocked until lifecycle and research gates pass")

    @router.post("/{import_id}/messages/{message_id}/approve")
    async def approve(import_id: str, message_id: str):
        return await run(service().approve, import_id, message_id)

    @router.post("/{import_id}/messages/{message_id}/correct")
    async def correct(import_id: str, message_id: str, correction: Correction):
        return await run(service().correct, import_id, message_id, correction.model_dump())

    def bridge(request):
        from services.historical_canonical_bridge import HistoricalCanonicalBridge

        lifecycle = getattr(request.app.state, "lifecycle", None)
        if lifecycle is None:
            raise HTTPException(423, "Canonical lifecycle unavailable")
        archive = service_factory() if service_factory is not None else ChatImportService()
        return HistoricalCanonicalBridge(archive, lifecycle)

    @router.post("/{import_id}/messages/{message_id}/canonical")
    async def canonical_promote(import_id: str, message_id: str, request: Request):
        return await run(bridge(request).promote, import_id, message_id)

    @router.get("/{import_id}/messages/{message_id}/canonical")
    async def canonical_link(import_id: str, message_id: str, request: Request):
        return await run(bridge(request).get, import_id, message_id)

    @router.get("/{import_id}/media")
    async def media(import_id: str, name: str):
        content = await run(service().media, import_id, name)
        return Response(content, media_type=mimetypes.guess_type(name)[0] or "application/octet-stream",
                        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})

    return router
