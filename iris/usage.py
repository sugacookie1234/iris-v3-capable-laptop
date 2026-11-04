"""Durable, content-free provider admission ledger; not a billing ledger."""
from contextlib import contextmanager, closing
from pathlib import Path
import sqlite3
import time
import uuid

_SESSION = uuid.uuid4().hex

class ProviderLimitError(ValueError):
    pass

class ProviderUsage:
    def __init__(self, path, settings=None, *, clock=time.time, session=None):
        self.path=Path(path)
        self.clock=clock
        self.session=session or _SESSION
        self.policy={}
        settings=settings or {}
        for key,default in [('HOUR',120),('DAY',500),('SESSION',500),('CONCURRENT',4)]:
            raw=settings.get('IRIS_PROVIDER_LIMIT_'+key,default)
            if isinstance(raw,bool) or not str(raw).isascii() or not str(raw).isdigit() or not 1<=int(raw)<=100000:
                raise ValueError('Invalid provider usage limit.')
            self.policy[key]=int(raw)

    def _connect(self):
        # Directory creation belongs to the trusted application launcher.
        db=sqlite3.connect(self.path,timeout=5,isolation_level=None)
        db.execute('CREATE TABLE IF NOT EXISTS provider_attempts (id TEXT PRIMARY KEY, category TEXT NOT NULL, session TEXT NOT NULL, started REAL NOT NULL, state TEXT NOT NULL)')
        return db

    @contextmanager
    def reserve(self, category):
        if category not in ('model','research','fish_tts','fish_asr','diagnostic'):
            raise ValueError('Unknown provider usage category.')
        identifier=uuid.uuid4().hex
        now=self.clock()
        try:
            with closing(self._connect()) as db:
                db.execute('BEGIN IMMEDIATE')
                hour,day,session,active=db.execute(
                    "SELECT COALESCE(SUM(started>=?),0), COALESCE(SUM(started>=?),0), COALESCE(SUM(session=?),0), COALESCE(SUM(state='reserved'),0) FROM provider_attempts WHERE category=?",
                    (now-3600,now-86400,self.session,category)).fetchone()
                if any(value>=self.policy[key] for value,key in zip((hour,day,session,active),('HOUR','DAY','SESSION','CONCURRENT'))):
                    raise ProviderLimitError('Local provider request budget exhausted. No request was sent. Unfinished reservations after a crash require owner review.')
                db.execute('INSERT INTO provider_attempts VALUES (?,?,?,?,?)',(identifier,category,self.session,now,'reserved'))
                db.execute("DELETE FROM provider_attempts WHERE started<? AND state!='reserved' AND session!=?",(now-86400,self.session))
                db.commit()
        except sqlite3.Error:
            raise ProviderLimitError('Provider usage accounting unavailable. No request was sent.') from None
        state='failed_or_cancelled'
        try:
            yield
            state='completed'
        finally:
            # Failure to record completion remains reserved: fail closed after a
            # crash/IO error, never infer whether the provider billed a request.
            try:
                with closing(self._connect()) as db:
                    db.execute('UPDATE provider_attempts SET state=? WHERE id=?',(state,identifier))
            except sqlite3.Error:
                raise ProviderLimitError('Provider result accounting failed. Do not automatically retry.') from None



def default_usage():
    """Trusted standalone default; no adapter can silently omit accounting."""
    from iris.local_config import config_path, effective_environment
    path=config_path().parent
    path.mkdir(parents=True,exist_ok=True)
    return ProviderUsage(path/'provider_usage.sqlite3',effective_environment())

def main(argv=None):
    """Explicit offline recovery; never called by startup or model tools."""
    import argparse
    parser=argparse.ArgumentParser(description='Inspect or release abandoned provider reservations. Stop IRIS first.')
    parser.add_argument('ledger',type=Path)
    parser.add_argument('--abandon',help='Exact reservation ID, after checking provider usage')
    parser.add_argument('--confirm-app-stopped',action='store_true')
    args=parser.parse_args(argv)
    if not args.ledger.is_file() or args.ledger.is_symlink():
        parser.error('Choose an existing regular provider ledger.')
    if args.abandon and not args.confirm_app_stopped:
        parser.error('Stop every IRIS process and pass --confirm-app-stopped.')
    with closing(sqlite3.connect(args.ledger)) as db:
        if args.abandon:
            cursor=db.execute("UPDATE provider_attempts SET state='owner_abandoned' WHERE id=? AND state='reserved'",(args.abandon,))
            if cursor.rowcount!=1:
                db.rollback()
                parser.error('Reservation is missing or no longer pending.')
            db.commit()
            print('Reservation released. Its admitted request still counts; billing remains unknown.')
        else:
            for row in db.execute("SELECT id,category,state FROM provider_attempts WHERE state='reserved'"):
                print(' '.join(row))
    return 0

if __name__=='__main__':
    raise SystemExit(main())
