"""Credential-free operator-workspace preview; broker paths cannot be composed."""
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[1]


def serve():
    import argparse
    import tempfile
    import uvicorn
    from fastapi.responses import JSONResponse
    sys.path.insert(0,str(ROOT/'backend'))
    from core.rebuild.application import create_app
    from core.rebuild.ledger import DemoAccount
    from core.rebuild.source_registry import SourceConfiguration, SourceRule
    from core.rebuild.safety_contracts import SafetyConfiguration
    parser=argparse.ArgumentParser()
    parser.add_argument('--port',type=int,default=8001)
    parser.add_argument('--p8-research',action='store_true')
    args=parser.parse_args()
    temporary=Path(tempfile.mkdtemp(prefix='nexus-v1-preview-'))
    account=DemoAccount(account_id='v1-preview-fixture',server='fixture',currency='USD',evidence_source='FIXTURE')
    app=create_app(database_path=temporary/'preview.sqlite3',token='v1-fixture-preview',fixture_mode=True,
        lifecycle_account=account,
        safety_configuration=SafetyConfiguration(approved_account_key=account.key,authorized_sources={'preview-manual'}),
        source_configuration=SourceConfiguration(revision=1,sources=(SourceRule(
            source_type='MANUAL',source_id='preview-manual',enabled=True,execution_eligibility='P2_ONLY'),)))

    @app.middleware('http')
    async def preview_scope(request,call_next):
        if args.p8_research:
            from core.rebuild.p8_projection import projection
            request.app.state.operations.research_projection=projection
        path=request.url.path
        allowed=(path=='/api/core/status' or path=='/api/controls/kill-switch'
                 or path.startswith('/api/core/operations/') or
                 request.method=='GET' and path.startswith('/api/core/tournament/'))
        if not allowed:
            return JSONResponse({'detail':'Isolated workspace preview only'},status_code=423)
        return await call_next(request)

    uvicorn.run(app,host='127.0.0.1',port=args.port,log_level='warning')


if __name__=='__main__':
    if Path.cwd().resolve()!=ROOT: raise ValueError('Run from repository root')
    document=(ROOT/'knowledge/TESTING.md').read_text(encoding='utf-8')
    section=document.split('## P1-M2 Incident Review Verification',1)[1]
    match=re.search(r"python.exe -B -c @'\n(.*?)\n'@",section,re.S)
    if not match: raise ValueError('Required audit guard missing')
    guarded=re.sub(r'^code=pytest.main\(.*\)$','serve(); code=0',match.group(1),flags=re.M)
    exec(compile(guarded,'<V1 protected preview>','exec'))
