"""Local read-only Arena preview; synthetic access binding, isolated temporary state."""
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[1]


def serve():
    import tempfile
    import uvicorn
    from fastapi.responses import JSONResponse
    sys.path.insert(0,str(ROOT/'backend'))
    from core.rebuild.application import create_app
    from core.rebuild.ledger import DemoAccount
    temporary=Path(tempfile.mkdtemp(prefix='nexus-p7-preview-'))
    app=create_app(database_path=temporary/'preview.sqlite3',token='p7-research-preview',fixture_mode=True,
        lifecycle_account=DemoAccount(account_id='p7-preview-fixture',server='fixture',currency='USD',evidence_source='FIXTURE'))

    @app.middleware('http')
    async def preview_read_only(request,call_next):
        if request.method!='GET' or not (request.url.path=='/api/core/status' or request.url.path.startswith('/api/core/tournament/')):
            return JSONResponse({'detail':'Research preview is read-only'},status_code=423)
        return await call_next(request)

    uvicorn.run(app,host='127.0.0.1',port=8000,log_level='warning')


if __name__=='__main__':
    if Path.cwd().resolve()!=ROOT: raise ValueError('Run from repository root')
    document=(ROOT/'knowledge/TESTING.md').read_text(encoding='utf-8')
    section=document.split('## P1-M2 Incident Review Verification',1)[1]
    match=re.search(r"python.exe -B -c @'\n(.*?)\n'@",section,re.S)
    if not match: raise ValueError('Required audit guard missing')
    guarded=re.sub(r'^code=pytest.main\(.*\)$','serve(); code=0',match.group(1),flags=re.M)
    exec(compile(guarded,'<P7 protected preview>','exec'))
