"""Transactional case persistence, separate from disposable market data.

Legacy migration is deliberately fail-closed. A backup and the original files
are retained; only a completely validated library receives a completion marker.
"""
from contextlib import contextmanager
import json
from pathlib import Path
import re
import shutil
import sqlite3
from uuid import uuid4


METADATA_FIELDS = ('id', 'title', 'stockCode', 'stockName', 'createdAt', 'updatedAt', 'tags')
EDITABLE_FIELDS = ('title', 'stockCode', 'stockName', 'tags', 'description', 'analysis', 'kline_data')


class CaseMigrationError(RuntimeError):
    """Legacy library needs repair before it can be imported safely."""


def validate_id(case_id):
    # Legacy IDs remain usable, but never become filesystem paths at runtime.
    if not isinstance(case_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', case_id):
        raise ValueError('非法案例 ID (unsafe case ID)')


def encode(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


class CaseStore:
    def __init__(self, db_path, legacy_dir):
        self.db_path = Path(db_path)
        self.legacy_dir = Path(legacy_dir)

    @contextmanager
    def connection(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path, timeout=30)
        try:
            # Serialize migration and read-modify-write updates across processes.
            conn.execute('BEGIN IMMEDIATE')
            conn.execute('CREATE TABLE IF NOT EXISTS cases (id TEXT PRIMARY KEY, document TEXT NOT NULL)')
            conn.execute('CREATE TABLE IF NOT EXISTS case_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
            if not conn.execute("SELECT 1 FROM case_settings WHERE key='legacy_migration'").fetchone():
                self._migrate(conn)
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _migrate(self, conn):
        source = self.legacy_dir
        backup = None
        warnings = []
        if source.exists():
            # Keep symlinks as symlinks in the backup, never follow them.
            if source.is_symlink():
                raise CaseMigrationError('案例迁移失败：legacy directory is a symlink')
            backup = self.db_path.parent / 'cases-legacy-backup-initial'
            if backup.is_symlink() or (backup.exists() and not backup.is_dir()):
                raise CaseMigrationError(f'案例迁移失败：unsafe backup location: {backup}')
            if not backup.exists():
                temporary = self.db_path.parent / ('.cases-backup-' + uuid4().hex)
                try:
                    shutil.copytree(source, temporary, symlinks=True)
                    temporary.rename(backup)
                except BaseException:
                    if temporary.exists():
                        shutil.rmtree(temporary)
                    raise
            try:
                # Repaired originals can be retried; the initial backup is immutable.
                documents, warnings = self._read_legacy(source)
            except (ValueError, OSError, UnicodeError) as exc:
                raise CaseMigrationError(f'案例迁移失败：{exc}；原文件保留，备份：{backup}') from exc
        else:
            documents = []
        for document in documents:
            conn.execute('INSERT INTO cases VALUES (?, ?)', (document['id'], encode(document)))
        conn.execute('INSERT INTO case_settings VALUES (?, ?)',
                     ('legacy_migration', encode({'count': len(documents), 'backup': str(backup) if backup else None, 'warnings': warnings})))

    def _read_legacy(self, source):
        index = source / 'index.json'
        if not index.exists():
            if any(source.iterdir()):
                raise ValueError('missing index.json with existing case files')
            return [], []
        if index.is_symlink():
            raise ValueError('unsafe symlink: index.json')
        try:
            metadata = json.loads(index.read_text(encoding='utf-8'))
        except (ValueError, UnicodeError) as exc:
            raise ValueError(f'index.json: {exc}') from exc
        if not isinstance(metadata, dict) or not isinstance(metadata.get('cases'), list):
            raise ValueError('index.json: cases must be a list')
        ids, documents, errors, warnings = set(), [], [], []
        for entry in metadata['cases']:
            try:
                if not isinstance(entry, dict):
                    raise ValueError('case metadata must be an object')
                case_id = entry.get('id')
                validate_id(case_id)
                if case_id in ids:
                    raise ValueError(f'duplicate case ID: {case_id}')
                ids.add(case_id)
                for field in METADATA_FIELDS:
                    if field not in entry:
                        raise ValueError(f'{case_id}: missing metadata {field}')
                directory = source / case_id
                if directory.is_symlink() or not directory.is_dir():
                    raise ValueError(f'{case_id}: missing directory or unsafe symlink')
                document = dict(entry)
                for field, filename in [('description', 'description.md'), ('analysis', 'analysis.json'),
                                        ('kline_data', 'kline_data.json')]:
                    path = directory / filename
                    if path.is_symlink():
                        raise ValueError(f'{case_id}/{filename}: unsafe symlink')
                    if not path.exists():
                        # The old writer made all three attachments optional and
                        # stored no manifest. Preserve omission, report ambiguity.
                        warnings.append(f'{case_id}/{filename}: 可选附件不存在，已按未提供迁移；旧格式无法区分未提供与文件丢失')
                        continue
                    if not path.is_file():
                        raise ValueError(f'{case_id}/{filename}: not a regular file')
                    try:
                        content = path.read_text(encoding='utf-8')
                        document[field] = content if field == 'description' else json.loads(content)
                    except (ValueError, UnicodeError) as exc:
                        raise ValueError(f'{case_id}/{filename}: {exc}') from exc
                validate_document(document)
                encode(document)
                documents.append(document)
            except (ValueError, OSError, UnicodeError) as exc:
                errors.append(str(exc))
        # Unindexed directories may contain cases lost by an interrupted old write.
        for path in source.iterdir():
            if path.name != 'index.json' and path.name not in ids:
                errors.append(f'unindexed legacy entry: {path.name}')
        if errors:
            raise ValueError('; '.join(errors))
        return documents, warnings

    def migration_status(self):
        with self.connection() as conn:
            raw = conn.execute("SELECT value FROM case_settings WHERE key='legacy_migration'").fetchone()[0]
        return json.loads(raw)

    def list(self):
        with self.connection() as conn:
            # Do not materialize every saved K-line array just to render the list.
            rows = conn.execute("SELECT json_remove(document, '$.description', '$.analysis', '$.kline_data') "
                                'FROM cases ORDER BY rowid DESC').fetchall()
        return [{key: doc[key] for key in METADATA_FIELDS} for (raw,) in rows for doc in [json.loads(raw)]]

    def get(self, case_id):
        validate_id(case_id)
        with self.connection() as conn:
            row = conn.execute('SELECT document FROM cases WHERE id=?', (case_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def create(self, document):
        raw = encode(document)
        with self.connection() as conn:
            conn.execute('INSERT INTO cases VALUES (?, ?)', (document['id'], raw))
        return json.loads(raw)

    def update(self, case_id, changes):
        validate_id(case_id)
        with self.connection() as conn:
            row = conn.execute('SELECT document FROM cases WHERE id=?', (case_id,)).fetchone()
            if row is None:
                return None
            document = json.loads(row[0])
            document.update(changes)
            validate_document(document)
            raw = encode(document)
            conn.execute('UPDATE cases SET document=? WHERE id=?', (raw, case_id))
        return json.loads(raw)

    def delete(self, case_id):
        validate_id(case_id)
        with self.connection() as conn:
            cursor = conn.execute('DELETE FROM cases WHERE id=?', (case_id,))
            return cursor.rowcount > 0


def validate_document(document):
    for field in ('title', 'stockCode', 'stockName', 'createdAt', 'updatedAt'):
        if not isinstance(document.get(field), str) or not document[field].strip():
            raise ValueError(f'字段 {field} 必须是非空字符串')
    if not isinstance(document.get('tags'), list) or not all(isinstance(tag, str) for tag in document['tags']):
        raise ValueError('字段 tags 必须是字符串列表')
    if 'description' in document and not isinstance(document['description'], str):
        raise ValueError('字段 description 必须是字符串')
    for field in ('analysis', 'kline_data'):
        if field in document and not isinstance(document[field], dict):
            raise ValueError(f'字段 {field} 必须是对象')
    if 'kline_data' in document:
        data = document['kline_data'].get('data', [])
        if not isinstance(data, list) or not all(isinstance(row, dict) for row in data):
            raise ValueError('字段 kline_data.data 必须是对象列表')
