"""Authenticated V1 workspace, with no native execution activation endpoint."""
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from .operations import ControlCommand, DeploymentCommand
from .source_ingestion import SourceSubmission


class Ack(BaseModel):
    model_config = ConfigDict(extra='forbid')
    command_id: str = Field(min_length=8, max_length=128)


def operations_router(access):
    router = APIRouter(prefix='/api/core/operations', dependencies=[Depends(access)])

    def invoke(method, *args, **kwargs):
        try:
            return method(*args, **kwargs)
        except KeyError:
            raise HTTPException(404, 'Record not found') from None
        except (ValueError, sqlite3.IntegrityError):
            raise HTTPException(409, 'Operation rejected: qualification, identity, configuration or evidence conflict') from None

    @router.get('/snapshot')
    @router.get('/export')
    def snapshot(request: Request, start: str | None = None, as_of: str | None = None):
        return invoke(request.app.state.operations.report, start=start, as_of=as_of)

    @router.get('/controls')
    def controls(request: Request):
        return invoke(request.app.state.operations.controls)

    @router.post('/controls')
    def control(command: ControlCommand, request: Request):
        return invoke(request.app.state.operations.set_controls, command)

    @router.post('/proposals')
    def propose(submission: SourceSubmission, request: Request):
        if submission.source_type != 'MANUAL':
            raise HTTPException(403, 'This endpoint accepts manual proposals only')
        return invoke(request.app.state.operations.ingest, submission)

    @router.post('/deployments')
    def deploy(command: DeploymentCommand, request: Request):
        return invoke(request.app.state.operations.deploy, command)

    @router.post('/whatsapp')
    def whatsapp(submission: SourceSubmission, request: Request):
        if submission.source_type != 'WHATSAPP_HUMAN':
            raise HTTPException(403, 'Connector accepts live human message envelopes only')
        return invoke(request.app.state.operations.ingest, submission)

    @router.post('/alerts/{alert_id}/acknowledge')
    def acknowledge(alert_id: str, body: Ack, request: Request):
        return invoke(request.app.state.operations.acknowledge, alert_id, body.command_id)

    return router
