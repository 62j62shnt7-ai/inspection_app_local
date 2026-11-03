"""Portable checksummed recovery packages and independent backup status."""
from contextlib import closing
from datetime import datetime, date, timezone
from pathlib import Path
import hashlib
import json
import os
import re
import secrets
import sqlite3
import tempfile
from zipfile import ZipFile, ZIP_DEFLATED, BadZipFile
from .store import serialized
from .backups import create_backup, restore_backup, compact_database_copy


def _settings(conn):
    conn.execute('CREATE TABLE IF NOT EXISTS backup_settings (id INTEGER PRIMARY KEY CHECK(id=1), contents TEXT NOT NULL)')
    row=conn.execute('SELECT contents FROM backup_settings WHERE id=1').fetchone()
    return json.loads(row[0]) if row else {}


def _save_settings(conn,settings):
    conn.execute('INSERT OR REPLACE INTO backup_settings VALUES (1,?)',(json.dumps(settings),))


@serialized
def invalidate_deleted_local_backup(store,deleted_paths):
    deleted={str(Path(path).resolve()) for path in deleted_paths}
    if not deleted:return False
    with closing(sqlite3.connect(store.db_path)) as conn,conn:
        settings=_settings(conn)
        recorded=settings.get('local_path')
        if not recorded or str(Path(recorded).resolve()) not in deleted:return False
        for key in ('day','local_path','local_at'):settings.pop(key,None)
        settings['local_success']=False
        _save_settings(conn,settings)
        return True


@serialized
def backup_status(store):
    with closing(sqlite3.connect(store.db_path)) as conn,conn:
        return _settings(conn)


@serialized
def configure_backup_folder(store,folder):
    if not isinstance(folder,str) or not folder.strip(): raise ValueError('Enter an existing folder path')
    destination=Path(folder).expanduser().resolve()
    if not destination.is_dir(): raise ValueError('Choose an existing writable folder')
    if destination==Path(store.db_path).resolve().parent or destination==Path(store.db_path).resolve().parent/'backups':
        raise ValueError('Choose a separate folder for the independent copy')
    # Complete authorized deletions while their original folder is still trusted.
    from .cleanup import recover_pending_cleanup
    try:
        recover_pending_cleanup(store)
    except OSError as exc:
        raise ValueError('Pending cleanup could not finish; release the file and retry.') from exc
    # Prove access without overwriting user files.
    with tempfile.TemporaryFile(dir=destination): pass
    with closing(sqlite3.connect(store.db_path)) as conn,conn:
        settings=_settings(conn)
        if settings.get('folder')!=str(destination) or not settings.get('independent_success'):
            for key in ('day','independent_at','independent_path'):settings.pop(key,None)
            settings.update(independent_success=False,error='Backup folder selected. Run Back up and test copy to verify it.')
        settings['folder']=str(destination);_save_settings(conn,settings)
    return backup_status(store)


@serialized
def export_master_package(store,destination,allow_missing_sources=False):
    destination=Path(destination)
    with tempfile.TemporaryDirectory() as tmp:
        database=Path(tmp)/'master.db'
        compact_database_copy(store.db_path, database)
        files={'master.db':database}
        unavailable=set()
        relocations={}
        with closing(sqlite3.connect(database)) as conn:
            has_batches=conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='import_batches'").fetchone()
            required={digest for digest,raw in conn.execute("SELECT digest,contents FROM import_batches WHERE state IN ('committed','staged')") if not any(json.loads(raw).get(key) for key in ('evidence_deleted','source_archive_deleted'))} if has_batches else set()
        for digest in required:
            archive=Path(store.db_path).parent/'source-archives'/(digest+'.xlsx')
            if not archive.is_file():
                if not allow_missing_sources:raise ValueError('Required source archive is missing: '+digest)
                unavailable.add(digest)
        archives=Path(store.db_path).parent/'source-archives'
        if archives.is_dir():
            for path in archives.glob('*.xlsx'):
                if path.is_symlink(): raise ValueError('Source archive cannot be a symbolic link')
                actual=hashlib.sha256(path.read_bytes()).hexdigest()
                if actual!=path.stem:
                    if not allow_missing_sources or not re.fullmatch(r'[a-f0-9]{64}',path.stem):
                        raise ValueError('Source archive checksum mismatch: '+path.name)
                    # Preserve damaged bytes, without pretending that they are
                    # the original workbook identified by the database digest.
                    unavailable.add(path.stem);relocations[path.stem]=actual
                files['source-archives/'+actual+'.xlsx']=path
        manifest={'format':'inspection-master-recovery','version':1,'created_at':datetime.now(timezone.utc).isoformat(),
                  'files':{name:hashlib.sha256(path.read_bytes()).hexdigest() for name,path in files.items()}}
        # Misnamed archives may supply another expected digest (including a
        # pair of swapped files). Availability describes the final package.
        unavailable.difference_update(name.split('/')[-1][:-5] for name in files if name.startswith('source-archives/'))
        if unavailable:manifest['unavailable_sources']=sorted(unavailable)
        if relocations:manifest['source_relocations']=relocations
        fd,temporary=tempfile.mkstemp(dir=destination.parent,suffix='.partial');os.close(fd)
        try:
            with ZipFile(temporary,'w',ZIP_DEFLATED) as package:
                package.writestr('manifest.json',json.dumps(manifest,ensure_ascii=False))
                for name,path in files.items():package.write(path,name)
            validate_restore_package(temporary)
            os.replace(temporary,destination)
        finally:Path(temporary).unlink(missing_ok=True)
    return destination


def validate_restore_package(path):
    try:
        with ZipFile(path) as package:
            names=package.namelist()
            if len(names)!=len(set(names)): raise ValueError('Duplicate recovery package entries')
            if sum(info.file_size for info in package.infolist())>1024*1024*1024: raise ValueError('Recovery package is too large')
            manifest=json.loads(package.read('manifest.json'))
            if not isinstance(manifest,dict) or manifest.get('format')!='inspection-master-recovery' or manifest.get('version')!=1 or not isinstance(manifest.get('files'),dict) or 'master.db' not in manifest['files']:
                raise ValueError('Unsupported recovery package')
            unavailable=manifest.get('unavailable_sources',[])
            if not isinstance(unavailable,list) or any(not isinstance(digest,str) or not re.fullmatch(r'[a-f0-9]{64}',digest) for digest in unavailable) or len(set(unavailable))!=len(unavailable):
                raise ValueError('Invalid unavailable-source inventory')
            if any('source-archives/'+digest+'.xlsx' in manifest['files'] for digest in unavailable):
                raise ValueError('Unavailable source is also present in recovery inventory')
            relocations=manifest.get('source_relocations',{})
            if not isinstance(relocations,dict) or any(not re.fullmatch(r'[a-f0-9]{64}',old) or not isinstance(new,str) or not re.fullmatch(r'[a-f0-9]{64}',new) or old==new or 'source-archives/'+new+'.xlsx' not in manifest['files'] for old,new in relocations.items()):
                raise ValueError('Invalid source relocation inventory')
            if set(names)!=set(manifest['files'])|{'manifest.json'}: raise ValueError('Recovery package inventory mismatch')
            for name,digest in manifest['files'].items():
                if name!='master.db' and not (name.startswith('source-archives/') and len(name.split('/'))==2 and name.split('/')[1]==digest+'.xlsx'):
                    raise ValueError('Unsafe recovery package entry')
                if hashlib.sha256(package.read(name)).hexdigest()!=digest: raise ValueError('Recovery package checksum mismatch')
            with tempfile.TemporaryDirectory() as tmp:
                database=Path(tmp)/'master.db';database.write_bytes(package.read('master.db'))
                with closing(sqlite3.connect(database)) as conn:
                    has_batches=conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='import_batches'").fetchone()
                    if has_batches:
                        for digest,raw in conn.execute("SELECT digest,contents FROM import_batches WHERE state IN ('committed','staged')"):
                            if not any(json.loads(raw).get(key) for key in ('evidence_deleted','source_archive_deleted')) and digest not in unavailable and 'source-archives/'+digest+'.xlsx' not in manifest['files']:raise ValueError('Required source archive is missing from recovery package')
            return manifest
    except (BadZipFile,KeyError,TypeError,json.JSONDecodeError) as exc:
        raise ValueError('Invalid recovery package') from exc


@serialized
def restore_master_package(store,path):
    manifest=validate_restore_package(path)
    # Validate the database before installing any archives or replacing live data.
    with tempfile.TemporaryDirectory() as tmp,ZipFile(path) as package:
        database=Path(tmp)/'master.db';database.write_bytes(package.read('master.db'))
        from .backups import validate_database
        validate_database(store,database)
        folder=Path(store.db_path).parent/'source-archives'
        if folder.is_symlink(): raise ValueError('Source archive folder cannot be a symbolic link')
        folder.mkdir(exist_ok=True)
        # Preserve the pre-restore database and even damaged source bytes before
        # replacing any archive. Publish to a unique path, never over a copy.
        copies=Path(store.db_path).parent/'recovery-copies'
        if copies.is_symlink(): raise ValueError('Recovery folder cannot be a symbolic link')
        copies.mkdir(exist_ok=True)
        for _ in range(100):
            safety=copies/('inspection-recovery-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+secrets.token_hex(4)+'.zip')
            try:
                fd=os.open(safety,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
                os.close(fd)
                break
            except FileExistsError:
                continue
        else:
            raise ValueError('Could not allocate a unique recovery protection name')
        try:
            export_master_package(store,safety,allow_missing_sources=True)
        except BaseException:
            safety.unlink(missing_ok=True)
            raise
        installed=[]
        replaced=[]
        try:
            for name in manifest['files']:
                if not name.startswith('source-archives/'):continue
                target=folder/Path(name).name
                if target.is_symlink(): raise ValueError('Source archive cannot be a symbolic link')
                if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest()==manifest['files'][name]:
                    continue
                fd,temporary=tempfile.mkstemp(dir=folder,suffix='.partial')
                try:
                    with os.fdopen(fd,'wb') as stream:stream.write(package.read(name));stream.flush();os.fsync(stream.fileno())
                    if target.exists():
                        fd,old_name=tempfile.mkstemp(dir=folder,prefix='.restore-',suffix='.partial')
                        old=Path(old_name)
                        with os.fdopen(fd,'wb') as stream:
                            stream.write(target.read_bytes());stream.flush();os.fsync(stream.fileno())
                        replaced.append((target,old))
                    else:
                        installed.append(target)
                    os.replace(temporary,target)
                finally:Path(temporary).unlink(missing_ok=True)
            result=restore_backup(store,database)
        except Exception:
            for target in installed:target.unlink(missing_ok=True)
            for target,old in replaced:os.replace(old,target)
            raise
        else:
            for _,old in replaced:old.unlink(missing_ok=True)
    if manifest.get('unavailable_sources') and not result.get('warning'):
        result['warning']='This package records '+str(len(manifest['unavailable_sources']))+' source archives as unavailable when it was created.'
    return {**result,'archives_restored':len(installed)+len(replaced),'safety_package':str(safety)}


@serialized
def automatic_backup(store,force=False):
    settings=backup_status(store)
    today=date.today().isoformat()
    if not force and settings.get('day')==today:return settings
    local=create_backup(store, compress=True)
    settings.update(day=today,local_success=True,local_path=str(local),local_at=datetime.now(timezone.utc).isoformat(),independent_success=False,error=None)
    folder=settings.get('folder')
    if folder:
        try:
            destination=Path(folder)
            if not destination.is_dir():raise ValueError('Independent backup folder is unavailable')
            target=destination/('inspection-recovery-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+secrets.token_hex(4)+'.zip')
            export_master_package(store,target)
            settings.update(independent_success=True,independent_at=datetime.now(timezone.utc).isoformat(),independent_path=str(target))
        except (OSError,ValueError,sqlite3.DatabaseError) as exc:
            settings['error']=str(exc)
    else:settings['error']='Choose an independent backup folder in Data & backups'
    with closing(sqlite3.connect(store.db_path)) as conn,conn:_save_settings(conn,settings)
    return settings
