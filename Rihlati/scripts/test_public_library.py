"""Synthetic export checks; no live database, original book, or external API."""
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
import zipfile
from export_public_library import export_library, SOURCE_FIELDS, PAGE_FIELDS, PASSAGE_FIELDS


class PublicLibraryTests(unittest.TestCase):
    def test_export_is_allowlisted_and_preserves_review_state(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'book.pdf').write_bytes(b'%PDF-1.4 synthetic fixture')
            database = root / 'test.sqlite3'
            connection = sqlite3.connect(database)
            for table, fields in [('sources', SOURCE_FIELDS + ('file_path', 'uploaded_by_user_id')),
                                  ('pages', PAGE_FIELDS), ('passages', PASSAGE_FIELDS)]:
                connection.execute('CREATE TABLE ' + table + '(' + ','.join(f + ' TEXT' for f in fields) + ')')
            connection.execute('CREATE TABLE users (password TEXT, email TEXT)')
            connection.execute("INSERT INTO users VALUES ('PRIVATE-CREDENTIAL-SENTINEL','PRIVATE-CONTACT-SENTINEL')")
            connection.execute("INSERT INTO sources (id,title,status,file_path,uploaded_by_user_id) VALUES ('book-1','Public fixture','pending','book.pdf','PRIVATE-USER-SENTINEL')")
            connection.execute("INSERT INTO pages (source_id,page_number,raw_text) VALUES ('book-1','1','Public page')")
            connection.execute("INSERT INTO passages (source_id,page_number,content) VALUES ('book-1','1','Public passage')")
            connection.commit()
            connection.close()
            before = database.read_bytes()
            output = root / 'export.zip'
            report = export_library(database, output, root)
            self.assertEqual(report['sources'], 1)
            self.assertEqual(database.read_bytes(), before)
            with zipfile.ZipFile(output) as archive:
                self.assertEqual(len(archive.namelist()), 3)
                payload = archive.read('library.json')
                self.assertNotIn(b'PRIVATE-', payload)
                bundle = json.loads(payload)
                self.assertEqual(bundle['sources'][0]['status'], 'pending')
                self.assertNotIn('file_path', bundle['sources'][0])
                self.assertEqual(bundle['pages'][0]['source_id'], 'book-1')
                self.assertEqual(set(bundle), {'format','exported_at','sources','pages','passages'})
            with self.assertRaises(FileExistsError):
                export_library(database, output, root)


if __name__ == '__main__':
    unittest.main()
