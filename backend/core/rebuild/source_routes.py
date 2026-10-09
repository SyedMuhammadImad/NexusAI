"""Authenticated P4 ingestion. Request bodies are not logged or echoed in errors."""
import sqlite3
from fastapi import APIRouter, Depends, HTTPException, Request
from .source_ingestion import SourceSubmission


def source_router(access):
    router=APIRouter(prefix='/api/core/sources',dependencies=[Depends(access)])

    @router.post('/ingest')
    def ingest(body: SourceSubmission,request: Request):
        service=request.app.state.sources
        if service is None: raise HTTPException(423,'P4 source integration not configured')
        try:
            return service.ingest(body)
        except (ValueError,KeyError,sqlite3.IntegrityError):
            raise HTTPException(409,'Source rejected: identity, provenance, timestamp or replay conflict') from None

    return router
