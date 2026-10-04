"""Export only book sources/pages/passages, never a copy of the private database.

Distribution permission must be confirmed before publishing the output. Reads a
consistent snapshot; never migrates, modifies or replaces the live database.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE_FIELDS = ('id', 'title', 'language', 'file_name', 'page_count', 'imported_at',
                 'status', 'level', 'subject', 'collection', 'processing_status')
PAGE_FIELDS = ('source_id', 'page_number', 'extraction_status', 'raw_text', 'confidence', 'kind', 'extraction_method')
PASSAGE_FIELDS = ('source_id', 'page_number', 'chunk_index', 'language', 'content')


def file_hash(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def rows(connection, table, fields, order):
    return [dict(row) for row in connection.execute(f"SELECT {','.join(fields)} FROM {table} ORDER BY {order}")]


def export_library(database, output, root=ROOT):
    database, output, root = Path(database).resolve(), Path(output).resolve(), Path(root).resolve()
    if output.exists():
        raise FileExistsError('Refusing to overwrite an existing archive')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='rihlati-library-export-') as temporary:
        snapshot = sqlite3.connect(str(Path(temporary) / 'snapshot.sqlite3'))
        live = sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)
        try:
            live.backup(snapshot)
        finally:
            live.close()
        snapshot.row_factory = sqlite3.Row
        try:
            sources = rows(snapshot, 'sources', SOURCE_FIELDS, 'id')
            paths = dict(snapshot.execute('SELECT id,file_path FROM sources'))
            pages = rows(snapshot, 'pages', PAGE_FIELDS, 'source_id,page_number')
            passages = rows(snapshot, 'passages', PASSAGE_FIELDS, 'source_id,page_number,chunk_index')
        finally:
            snapshot.close()
        files = {}
        for source in sources:
            path = (root / paths[source['id']]).resolve()
            if not path.is_relative_to(root) or not path.is_file() or path.suffix.lower() != '.pdf':
                raise ValueError('Source file missing, outside the project, or not PDF: ' + source['id'])
            digest = file_hash(path)
            source.update(sha256=digest, archive_path=f'files/{digest}.pdf', size_bytes=path.stat().st_size)
            files[digest] = path
        bundle = dict(format='rihlati-public-library-v1',
                      exported_at=datetime.now(timezone.utc).isoformat(),
                      sources=sources, pages=pages, passages=passages)
        # Explicit allowlists above exclude accounts, sessions, contacts, tickets,
        # messages, audits, reviewer/user IDs and learned private corrections.
        with zipfile.ZipFile(output, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=3) as archive:
            archive.writestr('library.json', json.dumps(bundle, ensure_ascii=False, indent=2))
            archive.writestr('README.txt',
                'Rihlati library - Team Siraj\n'
                'Published with project owner distribution permission. Book rights remain with their owners.\n'
                'This is NOT a database backup. It contains only PDFs and allowlisted source/page/passage data.\n'
                'No accounts, sessions, conversations, tickets, API keys or private learned corrections are included.\n'
                'Source approval and page extraction statuses are preserved: do not treat pending material as trusted.\n'
                'Read library.json for the title, language, source/page provenance and SHA-256 of each PDF.\n'
                'For a new installation, import PDFs using the admin library interface and review before approval.\n'
                'Never replace a live database with this package.\n')
            for digest, path in sorted(files.items()):
                archive.write(path, f'files/{digest}.pdf')
        with zipfile.ZipFile(output) as archive:
            if archive.testzip() is not None:
                raise ValueError('Archive integrity check failed; do not publish')
            for digest in files:
                with archive.open(f'files/{digest}.pdf') as stream:
                    if hashlib.file_digest(stream, 'sha256').hexdigest() != digest:
                        raise ValueError('Source changed during export; do not publish')
        return dict(sources=len(sources), pages=len(pages), passages=len(passages),
                    files=len(files), size_bytes=output.stat().st_size, sha256=file_hash(output))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, default=ROOT / 'data/rihlati.sqlite3')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(export_library(args.database, args.output), indent=2))


if __name__ == '__main__':
    main()
