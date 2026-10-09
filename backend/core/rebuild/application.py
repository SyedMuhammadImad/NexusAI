"""Review-only entry point. No legacy agents, broker adapter or training services start."""
import hmac
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from services.chat_import_routes import chat_import_router
from .ledger import Ledger
from .lifecycle_routes import lifecycle_router
from .lifecycle_service import LifecycleService


def create_app(*, database_path=None, token=None, lifecycle_account=None, fixture_mode=False, historical_service_factory=None,
               safety_configuration=None, safety_input_provider=None, safety_configuration_revision="1",
               execution_adapter=None, execution_clock=None, source_configuration=None, source_clock=None,
               tournament_reader=None, whatsapp_connector_token=None):
    if source_configuration is not None and execution_adapter is not None:
        raise ValueError('P4 broker execution is hard disabled')
    if execution_adapter is not None and (not fixture_mode or execution_adapter.scope != 'FIXTURE'
                                         or safety_configuration is None or token is None):
        raise ValueError('P3 app composition requires explicit fixture mode, token and P2 configuration')
    if safety_configuration is not None and (database_path is None or lifecycle_account is None):
        raise ValueError("P2 requires explicit database and account evidence")
    if fixture_mode and database_path is None:
        raise ValueError("Fixture lifecycle requires an explicit isolated database path")
    if lifecycle_account is not None and lifecycle_account.evidence_source != "FIXTURE":
        raise ValueError("P1 application binding accepts synthetic FIXTURE accounts only")
    control_token = os.getenv("CONTROL_TOKEN", "") if token is None else token
    if token is None and not control_token:
        local_token = Path(__file__).resolve().parents[2] / "private/control_token.txt"
        if local_token.exists():
            control_token = local_token.read_text(encoding="utf-8").strip()

    def access(request: Request, x_control_token: str | None = Header(default=None)):
        if request.url.path == '/api/core/operations/whatsapp':
            supplied = request.headers.get('x-connector-token', '')
            if not whatsapp_connector_token or not hmac.compare_digest(supplied, whatsapp_connector_token):
                raise HTTPException(403, 'A valid connector credential is required')
            return
        if not control_token or not hmac.compare_digest(x_control_token or "", control_token):
            raise HTTPException(403, "A valid local control token is required")

    @asynccontextmanager
    async def lifespan(app):
        path = database_path or Path(__file__).resolve().parents[2] / "data/lifecycle/core.sqlite3"
        app.state.ledger = Ledger(path, account=lifecycle_account)
        app.state.ledger.halt("Controlled rebuild: execution and model training disabled")
        app.state.lifecycle = LifecycleService(app.state.ledger, fixture_mode=fixture_mode, p2=safety_configuration is not None)
        from .safety import SafetyEngine
        app.state.safety = SafetyEngine(app.state.ledger, safety_configuration, configuration_revision=safety_configuration_revision) if safety_configuration is not None else None
        app.state.safety_input_provider = safety_input_provider
        from .source_ingestion import SourceIngestion
        from .source_registry import SourceConfiguration, active
        config=source_configuration
        if config is None and lifecycle_account is None and execution_adapter is None:
            with app.state.ledger.connect() as conn:
                config=active(conn) or SourceConfiguration()
        app.state.sources=SourceIngestion(app.state.ledger,config,clock=source_clock) if config is not None else None
        from .execution import ExecutionEngine
        app.state.execution = ExecutionEngine(app.state.safety, execution_adapter, clock=execution_clock) if execution_adapter is not None else None
        from .operations import Operations
        app.state.operations = Operations(app.state.ledger, sources=app.state.sources,
                                          safety=app.state.safety, provider=safety_input_provider,
                                          clock=source_clock)
        yield

    app = FastAPI(title="NexusAI Controlled Rebuild", version="2.0.0-rebuild",
                  description="Demo-only target. Execution disabled. Historical records are unverified evidence.",
                  lifespan=lifespan, dependencies=[Depends(access)], docs_url=None, redoc_url=None, openapi_url=None)
    from fastapi.exceptions import RequestValidationError
    from fastapi.exception_handlers import request_validation_exception_handler

    @app.exception_handler(RequestValidationError)
    async def source_validation_error(request,exc):
        if request.url.path.startswith(('/api/core/sources/', '/api/core/operations/')):
            return JSONResponse({'detail':'Invalid source payload'},status_code=422)
        return await request_validation_exception_handler(request,exc)
    app.add_middleware(CORSMiddleware, allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
                       allow_methods=["GET", "POST"], allow_headers=["Content-Type", "X-Control-Token"])

    @app.middleware("http")
    async def freeze(request: Request, call_next):
        if request.method != "OPTIONS":
            try:
                access(request, request.headers.get("x-control-token"))
            except HTTPException:
                return JSONResponse({"detail": "A valid local control token is required"}, status_code=403)
        # Allowlist writes rather than trying to enumerate every legacy bypass.
        path = request.url.path
        allowed = (path == "/api/private/chat-imports" or path == "/api/controls/kill-switch"
                   or (path.startswith("/api/private/chat-imports/") and "/messages/" in path
                       and path.endswith(("/correct", "/approve", "/canonical"))))
        lifecycle_write = path in {"/api/core/lifecycle/sources", "/api/core/lifecycle/signals",
                                   "/api/core/lifecycle/intents", "/api/core/lifecycle/requests", "/api/core/sources/ingest"}
        segments = path.strip("/").split("/")
        lifecycle_write |= (len(segments) == 6 and segments[:4] == ["api", "core", "lifecycle", "intents"]
                            and segments[-1] == "evaluate")
        if execution_adapter is not None:
            lifecycle_write |= path == '/api/core/lifecycle/reconcile' or (
                len(segments)==6 and segments[:4]==['api','core','lifecycle','requests'] and segments[-1]=='submit')
        allowed |= request.method == "POST" and lifecycle_write
        operation_write = path in {'/api/core/operations/controls', '/api/core/operations/proposals',
                                   '/api/core/operations/deployments', '/api/core/operations/whatsapp'}
        operation_write |= (len(segments)==6 and segments[:4]==['api','core','operations','alerts']
                            and segments[-1]=='acknowledge')
        allowed |= request.method == 'POST' and operation_write
        try:
            size = int(request.headers.get("content-length", "0"))
        except ValueError:
            return JSONResponse({"detail": "Invalid request size"}, status_code=400)
        if size > 101 * 1024 * 1024:
            return JSONResponse({"detail": "Request too large"}, status_code=413)
        if request.method not in {"GET", "HEAD", "OPTIONS"} and not allowed:
            return JSONResponse({"detail": "Disabled by controlled rebuild gates", "execution_enabled": False}, status_code=423)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    app.include_router(chat_import_router(access, historical_service_factory))
    app.include_router(lifecycle_router(access))
    from .source_routes import source_router
    app.include_router(source_router(access))
    from .tournament_projection import tournament_router
    app.include_router(tournament_router(access,tournament_reader))
    from .operations_routes import operations_router
    app.include_router(operations_router(access))

    @app.get("/api/health")
    @app.get("/api/core/status")
    def status(request: Request):
        return {"status": "REBUILD_HALTED", "agents_running": 0, **request.app.state.ledger.status()}

    @app.post("/api/controls/kill-switch")
    def halt(request: Request):
        return request.app.state.ledger.halt("Manual operator halt; broker positions not closed")

    @app.websocket("/ws")
    async def websocket(ws: WebSocket):
        # Streaming is unavailable until authenticated fan-out is built and verified.
        await ws.close(code=1008, reason="Rebuild: streaming disabled")

    return app
