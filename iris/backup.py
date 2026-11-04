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
STORES=('memory.sqlite3','tasks.sqlite3','goals.sqlite3','organizer.sqlite3','action_history.sqlite3','jobs.sqlite3')

class BackupError(ValueError):
    pass

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
    source=Path(source).resolve(strict=True);destination=Path(destination).absolute()
    if destination.exists():raise BackupError('Backup destination already exists.')
    records={};total=0
    for name in STORES:
        path=source/name
        if not path.exists():continue
        if path.is_symlink() or not path.is_file() or path.stat().st_size>MAX_BYTES:
            raise BackupError('Unsupported or oversized source store.')
        deadline=time.monotonic()+15
        def progress(*_):
            if time.monotonic()>deadline:raise BackupError('Snapshot timed out; stop IRIS and try again.')
        with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) as origin, closing(sqlite3.connect(':memory:')) as snapshot:
            origin.backup(snapshot,pages=256,progress=progress)
            _integrity(snapshot)
            if name=='jobs.sqlite3':_jobs(snapshot,True)
            raw=snapshot.serialize()
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
    destination=Path(destination).absolute()
    if destination.exists():raise BackupError('Recovery requires a new destination folder.')
    archive=Path(archive)
    if archive.stat().st_size>MAX_BYTES*3:raise BackupError('Archive is too large.')
    raw=archive.read_bytes()
    if not raw.startswith(MAGIC) or len(raw)<len(MAGIC)+17:raise BackupError('Invalid archive.')
    offset=len(MAGIC)
    try:
        plaintext=_cipher(password,raw[offset:offset+16]).decrypt(raw[offset+16:])
        manifest=json.loads(plaintext)
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
                _integrity(snapshot)
                if name=='jobs.sqlite3':_jobs(snapshot,False)
                (stage/name).write_bytes(snapshot.serialize())
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
    except (ValueError,OSError,sqlite3.Error):
        parser.exit(1,'Backup/recovery failed; existing owner stores were not replaced.\n')
    print(f'{len(names)} stores verified. Keep the passphrase separately; it cannot be recovered by IRIS.')
    return 0

if __name__=='__main__':raise SystemExit(main())
