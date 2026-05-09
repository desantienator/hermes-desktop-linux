from __future__ import annotations
import json, shlex, subprocess, textwrap
from .models import ConnectionProfile, RemoteResult, now_ms

REMOTE_SCRIPT = r'''
import json, os, sqlite3, glob, pathlib, subprocess, sys, time
home = os.path.expanduser(os.environ.get('HERMES_HOME', '~/.hermes'))

def safe_read(path, limit=200000):
    try:
        with open(os.path.expanduser(path), 'r', encoding='utf-8', errors='replace') as f:
            return f.read(limit)
    except Exception as e:
        return None

def list_sessions():
    roots=[os.path.join(home,'sessions'), os.path.join(home,'logs'), home]
    rows=[]
    for root in roots:
        for pat in ('**/*.jsonl','**/*.json','**/*.md','**/*.txt'):
            for p in glob.glob(os.path.join(root,pat), recursive=True)[:2000]:
                try:
                    st=os.stat(p)
                    if st.st_size == 0: continue
                    rows.append({'path':p,'name':os.path.basename(p),'size':st.st_size,'mtime':st.st_mtime})
                except OSError: pass
    rows=sorted({r['path']:r for r in rows}.values(), key=lambda r:r['mtime'], reverse=True)[:300]
    return rows

def list_files(base=None):
    base=os.path.expanduser(base or home)
    out=[]
    for name in sorted(os.listdir(base))[:500]:
        p=os.path.join(base,name)
        try:
            st=os.stat(p)
            out.append({'name':name,'path':p,'is_dir':os.path.isdir(p),'size':st.st_size,'mtime':st.st_mtime})
        except OSError: pass
    return out

def list_skills():
    roots=[os.path.join(home,'skills'), os.path.expanduser('~/.hermes/skills')]
    out=[]
    for root in roots:
        for p in glob.glob(os.path.join(root,'**','SKILL.md'), recursive=True):
            txt=safe_read(p, 4000) or ''
            title=os.path.basename(os.path.dirname(p))
            desc=''
            for line in txt.splitlines()[:40]:
                if line.startswith('description:'):
                    desc=line.split(':',1)[1].strip().strip('"')
            out.append({'name':title,'path':p,'description':desc})
    return sorted({x['path']:x for x in out}.values(), key=lambda x:x['name'])

def cron_jobs():
    try:
        cp=subprocess.run(['hermes','cron','list','--json'], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
        if cp.returncode==0:
            return json.loads(cp.stdout)
        return {'error': cp.stderr or cp.stdout}
    except Exception as e:
        return {'error': str(e)}

def kanban():
    db=os.path.join(home,'kanban.db')
    if not os.path.exists(db): return {'boards': [], 'tasks': [], 'path': db, 'error':'kanban.db not found'}
    con=sqlite3.connect(db); con.row_factory=sqlite3.Row
    tables=[r[0] for r in con.execute("select name from sqlite_master where type='table'")]
    result={'path':db,'tables':tables,'boards':[],'tasks':[]}
    for t in tables:
        cols=[r[1] for r in con.execute(f'pragma table_info({t})')]
        if any(c in cols for c in ['title','name']) and any(c in cols for c in ['status','state','column_id','board_id']):
            try:
                result['tasks'] += [dict(r) for r in con.execute(f'select * from {t} limit 500')]
            except Exception: pass
        elif 'board' in t.lower():
            try: result['boards'] += [dict(r) for r in con.execute(f'select * from {t} limit 100')]
            except Exception: pass
    con.close(); return result

def usage():
    files=list_sessions()
    total=sum(x['size'] for x in files)
    return {'session_files':len(files),'bytes':total,'hermes_home':home,'recent':files[:20]}

def overview():
    return {'host':os.uname().nodename,'user':os.environ.get('USER',''),'hermes_home':home,'python':sys.version.split()[0],'has_hermes': subprocess.run('command -v hermes',shell=True,stdout=subprocess.PIPE).stdout.decode().strip()}

def read_path(path): return {'path': path, 'content': safe_read(path, 1000000)}
def write_path(path, content):
    pathlib.Path(os.path.expanduser(path)).write_text(content, encoding='utf-8')
    return {'saved': path}

action=os.environ.get('HD_ACTION','overview')
arg=os.environ.get('HD_ARG','')
payload=json.loads(os.environ.get('HD_PAYLOAD','{}'))
try:
    if action=='overview': data=overview()
    elif action=='sessions': data=list_sessions()
    elif action=='files': data=list_files(arg or None)
    elif action=='read': data=read_path(arg)
    elif action=='write': data=write_path(arg, payload.get('content',''))
    elif action=='skills': data=list_skills()
    elif action=='cron': data=cron_jobs()
    elif action=='kanban': data=kanban()
    elif action=='usage': data=usage()
    else: data={'error':'unknown action '+action}
    print(json.dumps({'ok': True, 'data': data}, default=str))
except Exception as e:
    print(json.dumps({'ok': False, 'error': repr(e)}))
'''

class SSHClient:
    def __init__(self, profile: ConnectionProfile):
        self.profile = profile

    def run_action(self, action: str, arg: str = "", payload: dict | None = None, timeout: int = 60) -> RemoteResult:
        start = now_ms()
        env = f"HERMES_HOME={shlex.quote(self.profile.hermes_home)} HD_ACTION={shlex.quote(action)} HD_ARG={shlex.quote(arg)} HD_PAYLOAD={shlex.quote(json.dumps(payload or {}))}"
        script = shlex.quote(REMOTE_SCRIPT)
        if self.profile.host in ("localhost", "127.0.0.1", "::1") and not self.profile.ssh_alias:
            cmd = f"{env} python3 -c {script}"
        else:
            port = [] if self.profile.ssh_alias else ["-p", str(self.profile.port)]
            remote_cmd = f"{env} python3 -c {script}"
            cmd = " ".join(["ssh", *map(shlex.quote, port), shlex.quote(self.profile.target), shlex.quote(remote_cmd)])
        try:
            cp = subprocess.run(cmd, shell=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
            elapsed = now_ms() - start
            if cp.returncode != 0:
                return RemoteResult(False, error=cp.stderr or cp.stdout, elapsed_ms=elapsed)
            parsed = json.loads(cp.stdout.strip().splitlines()[-1])
            return RemoteResult(bool(parsed.get('ok')), data=parsed.get('data'), error=parsed.get('error',''), elapsed_ms=elapsed)
        except Exception as e:
            return RemoteResult(False, error=str(e), elapsed_ms=now_ms()-start)
