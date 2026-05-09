from __future__ import annotations
import json, subprocess
from .models import ConnectionProfile, RemoteResult, now_ms

REMOTE_SCRIPT = r'''
import json, os, sqlite3, glob, subprocess, sys, shutil, re, tempfile
home = os.path.expanduser(os.environ.get('HERMES_HOME', '~/.hermes'))
home_real = os.path.realpath(home)

VALID_TABLE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')

def safe_read(path, limit=1000000):
    try:
        with open(os.path.expanduser(path), 'r', encoding='utf-8', errors='replace') as f:
            return f.read(limit)
    except Exception:
        return None

def list_sessions():
    roots=[os.path.join(home,'sessions'), os.path.join(home,'logs'), home]
    matches=[]
    for root in roots:
        for pat in ('**/*.jsonl','**/*.json','**/*.md','**/*.txt'):
            matches.extend(glob.glob(os.path.join(root,pat), recursive=True))
    rows=[]
    for p in sorted(set(matches)):
        try:
            st=os.stat(p)
            if st.st_size == 0: continue
            rows.append({'path':p,'name':os.path.basename(p),'size':st.st_size,'mtime':st.st_mtime})
        except OSError:
            pass
    return sorted(rows, key=lambda r:r['mtime'], reverse=True)[:300]

def list_files(base=None):
    base=os.path.expanduser(base or home)
    names=sorted(os.listdir(base))
    out=[]
    for name in names[:500]:
        p=os.path.join(base,name)
        try:
            st=os.stat(p)
            out.append({'name':name,'path':p,'is_dir':os.path.isdir(p),'size':st.st_size,'mtime':st.st_mtime})
        except OSError:
            pass
    if len(names) > 500:
        out.append({'name':'… truncated after 500 entries','path':base,'is_dir':False,'size':0,'mtime':0})
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

def table_columns(con, table):
    if not VALID_TABLE.match(table):
        return []
    return [r[1] for r in con.execute(f'pragma table_info({table})')]

def table_rows(con, table, limit):
    if not VALID_TABLE.match(table):
        return []
    return [dict(r) for r in con.execute(f'select * from {table} limit {int(limit)}')]

def kanban():
    db=os.path.join(home,'kanban.db')
    if not os.path.exists(db): return {'boards': [], 'tasks': [], 'path': db, 'error':'kanban.db not found'}
    con=sqlite3.connect(db); con.row_factory=sqlite3.Row
    tables=[r[0] for r in con.execute("select name from sqlite_master where type='table'")]
    result={'path':db,'tables':tables,'boards':[],'tasks':[]}
    for t in tables:
        cols=table_columns(con, t)
        if any(c in cols for c in ['title','name']) and any(c in cols for c in ['status','state','column_id','board_id']):
            try: result['tasks'] += table_rows(con, t, 500)
            except Exception: pass
        elif 'board' in t.lower():
            try: result['boards'] += table_rows(con, t, 100)
            except Exception: pass
    con.close(); return result

def usage():
    files=list_sessions()
    total=sum(x['size'] for x in files)
    return {'session_files':len(files),'bytes':total,'hermes_home':home,'recent':files[:20]}

def overview():
    return {'host':os.uname().nodename,'user':os.environ.get('USER',''),'hermes_home':home,'python':sys.version.split()[0],'has_hermes': shutil.which('hermes') or ''}

def read_path(path): return {'path': path, 'content': safe_read(path, 1000000)}

def write_path(path, content):
    encoded = content.encode('utf-8')
    if len(encoded) > 10 * 1024 * 1024:
        raise ValueError('refusing to write files larger than 10MB')
    target = os.path.realpath(os.path.expanduser(path))
    if not (target == home_real or target.startswith(home_real + os.sep)):
        raise PermissionError('writes are limited to HERMES_HOME')
    directory = os.path.dirname(target)
    fd, tmp = tempfile.mkstemp(prefix='.hermes-desktop-', suffix='.tmp', dir=directory, text=True)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(content)
        os.replace(tmp, target)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return {'saved': target}

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
        if self.profile.host in ("localhost", "127.0.0.1", "::1") and not self.profile.ssh_alias:
            cmd = ["python3", "-c", REMOTE_SCRIPT]
        else:
            port = [] if self.profile.ssh_alias else ["-p", str(self.profile.port)]
            cmd = ["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new", *port, self.profile.target, "python3", "-c", REMOTE_SCRIPT]
        env = {
            "HERMES_HOME": self.profile.hermes_home,
            "HD_ACTION": action,
            "HD_ARG": arg,
            "HD_PAYLOAD": json.dumps(payload or {}),
        }
        try:
            cp = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, env=env)
            elapsed = now_ms() - start
            if cp.returncode != 0:
                return RemoteResult(False, error=cp.stderr or cp.stdout, elapsed_ms=elapsed)
            parsed = json.loads(cp.stdout.strip().splitlines()[-1])
            return RemoteResult(bool(parsed.get('ok')), data=parsed.get('data'), error=parsed.get('error',''), elapsed_ms=elapsed)
        except Exception as e:
            return RemoteResult(False, error=str(e), elapsed_ms=now_ms()-start)
