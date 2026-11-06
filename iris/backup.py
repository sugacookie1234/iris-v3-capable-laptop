"""Explicit encrypted snapshots; never restores over a live data directory."""
import base64
from contextlib import closing
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import time

MAGIC=b'IRIS-BACKUP-1\0'
MAX_BYTES=64*1024*1024
STORES=('memory.sqlite3','tasks.sqlite3','goals.sqlite3','organizer.sqlite3','action_history.sqlite3','jobs.sqlite3','projects.sqlite3')

class BackupError(ValueError):
    pass


def _safe_path(path):
    path = Path(path).absolute()
    for item in (path, *path.parents):
        if item.is_symlink() or (hasattr(item, 'is_junction') and item.is_junction()):
            raise BackupError('Backup paths cannot use symbolic links or junctions.')
    return path


def _projects(db, portable):
    """Rebuild only validated envelopes in RAM, eliminating free-page plaintext.

    Portable JSON exists only inside the authenticated passphrase archive. Restore
    verifies fresh destination-account protection before any database reaches disk.
    """
    from iris.desktop.secrets import protect, unprotect
    from iris.generalist.continuity import ProjectContinuity
    schema = 'CREATE TABLE projects (id TEXT PRIMARY KEY, payload BLOB NOT NULL)'
    try:
        if db.execute('PRAGMA user_version').fetchone()[0] != 1:
            raise ValueError
        objects = db.execute('SELECT type,name,tbl_name,sql FROM sqlite_master').fetchall()
        expected = {('table','projects','projects'), ('index','sqlite_autoindex_projects_1','projects')}
        if len(objects) != 2 or {tuple(row[:3]) for row in objects} != expected:
            raise ValueError
        table_sql = next(row[3] for row in objects if row[0] == 'table')
        if ''.join(table_sql.lower().split()) != ''.join(schema.lower().split()):
            raise ValueError
        rows = db.execute('SELECT id,payload FROM projects LIMIT 11').fetchall()
        if len(rows) > 10:
            raise ValueError
        with closing(sqlite3.connect(':memory:')) as clean:
            clean.execute('PRAGMA temp_store=MEMORY')
            clean.execute(schema)
            clean.execute('PRAGMA user_version=1')
            for identifier, payload in rows:
                value = ProjectContinuity.decode_envelope(identifier, payload, unprotect if portable else lambda b:b)
                raw = json.dumps(value, separators=(',', ':'), allow_nan=False).encode()
                result = raw if portable else protect(raw)
                if ProjectContinuity.decode_envelope(identifier, result, (lambda b:b) if portable else unprotect) != value:
                    raise ValueError
                clean.execute('INSERT INTO projects VALUES (?,?)', (identifier, result))
            clean.commit()
            _integrity(clean)
            return clean.serialize()
    except Exception:
        raise BackupError('Protected project records are unreadable or incompatible. Keep the original store; '
                          'use the original Windows environment or a valid portable backup. Nothing was published.') from None

def _cipher(password,salt):
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
    if not isinstance(password,str) or not 12<=len(password)<=1024:
        raise BackupError('Use a recovery passphrase of 12 to 1024 characters.')
    key=Scrypt(salt=salt,length=32,n=2**17,r=8,p=1).derive(password.encode('utf-8'))
    return Fernet(base64.urlsafe_b64encode(key))

def _integrity(db):
    if db.execute('PRAGMA integrity_check').fetchall()!=[('ok',)]:
        raise BackupError('Database integrity verification failed.')

def _jobs(db,portable):
    from iris.desktop.secrets import protect, unprotect
    transform=unprotect if portable else protect
    # All payload conversion occurs in the in-memory snapshot, never live data.
    for identifier,topic,result in db.execute('SELECT id,topic,result FROM notes_jobs').fetchall():
        db.execute('UPDATE notes_jobs SET topic=?,result=? WHERE id=?',
            (transform(bytes(topic)),transform(bytes(result)) if result is not None else None,identifier))
    db.commit()

def create(source,destination,password,*,app_stopped=False):
    if not app_stopped:
        raise BackupError('Stop all IRIS processes before taking a multi-store snapshot.')
    source=_safe_path(source).resolve(strict=True);destination=_safe_path(destination)
    if destination.exists():raise BackupError('Backup destination already exists.')
    records={};total=0
    for name in STORES:
        path=source/name
        _safe_path(path)
        for suffix in ('-wal','-shm','-journal'):_safe_path(str(path)+suffix)
        if not path.exists():continue
        if path.is_symlink() or not path.is_file() or path.stat().st_size>MAX_BYTES:
            raise BackupError('Unsupported or oversized source store.')
        deadline=time.monotonic()+15
        def progress(*_):
            if time.monotonic()>deadline:raise BackupError('Snapshot timed out; stop IRIS and try again.')
        with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) as origin, closing(sqlite3.connect(':memory:')) as snapshot:
            origin.backup(snapshot,pages=256,progress=progress)
            snapshot.execute('PRAGMA trusted_schema=OFF')
            snapshot.execute('PRAGMA temp_store=MEMORY')
            _integrity(snapshot)
            if name=='jobs.sqlite3':_jobs(snapshot,True)
            raw=_projects(snapshot,True) if name=='projects.sqlite3' else snapshot.serialize()
        total+=len(raw)
        if total>MAX_BYTES:raise BackupError('Backup exceeds the 64 MiB database limit.')
        records[name]=base64.b64encode(raw).decode('ascii')
    if not records:raise BackupError('No supported stores found.')
    salt=os.urandom(16)
    plaintext=json.dumps({'version':1,'stores':records},separators=(',',':')).encode()
    cipher=_cipher(password,salt);encrypted=cipher.encrypt(plaintext)
    # Verify the exact ciphertext before publishing it. Only ciphertext touches disk.
    if cipher.decrypt(encrypted)!=plaintext:raise BackupError('Backup verification failed.')
    fd,stage=tempfile.mkstemp(prefix='.iris-backup-',dir=destination.parent)
    try:
        with os.fdopen(fd,'wb') as stream:
            stream.write(MAGIC+salt+encrypted);stream.flush();os.fsync(stream.fileno())
        # Atomic no-clobber publication on NTFS; unsupported filesystems fail safely.
        os.link(stage,destination)
    finally:
        Path(stage).unlink(missing_ok=True)
    return tuple(records)

def restore(archive,destination,password,*,app_stopped=False):
    from cryptography.fernet import InvalidToken
    if not app_stopped:raise BackupError('Stop IRIS before recovery.')
    destination=_safe_path(destination)
    if destination.exists():raise BackupError('Recovery requires a new destination folder.')
    archive=_safe_path(archive)
    if archive.stat().st_size>MAX_BYTES*3:raise BackupError('Archive is too large.')
    raw=archive.read_bytes()
    if not raw.startswith(MAGIC) or len(raw)<len(MAGIC)+17:raise BackupError('Invalid archive.')
    offset=len(MAGIC)
    try:
        plaintext=_cipher(password,raw[offset:offset+16]).decrypt(raw[offset+16:])
        from iris.generalist.continuity import unique_pairs
        manifest=json.loads(plaintext,object_pairs_hook=unique_pairs)
        if type(manifest) is not dict or set(manifest)!={'version','stores'} or type(manifest['version']) is not int or manifest['version']!=1:
            raise BackupError('Unsupported archive manifest.')
        stores=manifest['stores']
        if type(stores) is not dict or not stores or not set(stores)<=set(STORES):raise BackupError('Invalid store list.')
        decoded={name:base64.b64decode(value,validate=True) for name,value in stores.items()}
        if sum(map(len,decoded.values()))>MAX_BYTES:raise BackupError('Recovered stores exceed size limit.')
    except (InvalidToken,UnicodeError,TypeError,ValueError):
        raise BackupError('Wrong passphrase or invalid/tampered archive.') from None
    stage=Path(tempfile.mkdtemp(prefix='.iris-restore-',dir=destination.parent))
    try:
        for name,data in decoded.items():
            with closing(sqlite3.connect(':memory:')) as snapshot:
                snapshot.deserialize(data)
                snapshot.execute('PRAGMA trusted_schema=OFF')
                snapshot.execute('PRAGMA temp_store=MEMORY')
                _integrity(snapshot)
                if name=='jobs.sqlite3':_jobs(snapshot,False)
                protected=_projects(snapshot,False) if name=='projects.sqlite3' else snapshot.serialize()
                (stage/name).write_bytes(protected)
        if destination.exists():raise BackupError('Recovery destination appeared during staging.')
        os.rename(stage,destination)
    finally:
        if stage.exists():
            if stage.resolve().parent!=destination.parent.resolve() or not stage.name.startswith('.iris-restore-'):
                raise BackupError('Unexpected recovery staging location.')
            shutil.rmtree(stage)
    return tuple(decoded)

def main(argv=None):
    import argparse
    import getpass
    parser=argparse.ArgumentParser(description='Offline encrypted backup/recovery; stop IRIS first. Never overwrites data.')
    parser.add_argument('operation',choices=('create','restore'))
    parser.add_argument('source',type=Path);parser.add_argument('destination',type=Path)
    parser.add_argument('--confirm-app-stopped',action='store_true')
    args=parser.parse_args(argv)
    if not args.confirm_app_stopped:parser.error('Stop all IRIS processes and pass --confirm-app-stopped.')
    password=getpass.getpass('Recovery passphrase: ')
    if args.operation=='create' and password!=getpass.getpass('Confirm passphrase: '):parser.error('Passphrases differ.')
    try:
        names=globals()[args.operation](args.source,args.destination,password,app_stopped=True)
    except BackupError as error:
        parser.exit(1,str(error)+'\n')
    except (ValueError,OSError,sqlite3.Error):
        parser.exit(1,'Backup/recovery failed; existing owner stores were not replaced.\n')
    print(f'{len(names)} stores verified. Keep the passphrase separately; it cannot be recovered by IRIS.')
    return 0

if __name__=='__main__':raise SystemExit(main())
