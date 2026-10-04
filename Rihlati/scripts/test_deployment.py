"""Local deployment tests. No network, live database, or provider calls."""
import unittest
from waitress.adjustments import Adjustments
from waitress.proxy_headers import proxy_headers_middleware
from server_settings import waitress_options
from release_check import content_issues, path_issue


class DeploymentTests(unittest.TestCase):
    def options(self, **values):
        return waitress_options(lambda key, default='': values.get(key, default))

    def test_local_does_not_trust_proxy_headers(self):
        options = self.options()
        self.assertEqual(options['host'], '127.0.0.1')
        self.assertNotIn('trusted_proxy', options)
        self.assertTrue(Adjustments(**options).clear_untrusted_proxy_headers)

    def test_production_trusts_only_one_loopback_proxy(self):
        settings = Adjustments(**self.options(RIHLATI_ENV='production', RIHLATI_TRUST_PROXY='loopback'))
        self.assertEqual(settings.trusted_proxy, '127.0.0.1')
        self.assertEqual(settings.trusted_proxy_count, 1)
        self.assertEqual(settings.trusted_proxy_headers, {'x-forwarded-for', 'x-forwarded-proto'})

    def test_public_binding_and_unsafe_proxy_settings_fail_closed(self):
        for values in ({'RIHLATI_HOST': '0.0.0.0'},
                       {'RIHLATI_ENV': 'production', 'RIHLATI_HOST': '0.0.0.0'},
                       {'RIHLATI_TRUST_PROXY': 'loopback'},
                       {'RIHLATI_ENV': 'production', 'RIHLATI_TRUST_PROXY': '*'},
                       {'RIHLATI_ENV': 'production', 'RIHLATI_TRUST_PROXY': 'loopback', 'RIHLATI_HOST': 'localhost'}):
            with self.subTest(values=values), self.assertRaises(RuntimeError):
                self.options(**values)

    def test_invalid_ports_rejected(self):
        for port in ('0', '65536', 'not-a-port'):
            with self.assertRaises(ValueError):
                self.options(PORT=port)

    def forwarded(self, peer, trusted=True):
        captured = {}
        def app(environ, start_response):
            captured.update(environ)
            start_response('200 OK', [])
            return [b'OK']
        options = self.options(**({'RIHLATI_ENV': 'production', 'RIHLATI_TRUST_PROXY': 'loopback'} if trusted else {}))
        middleware = proxy_headers_middleware(app, trusted_proxy=options.get('trusted_proxy'),
            trusted_proxy_count=1, trusted_proxy_headers=options.get('trusted_proxy_headers'), clear_untrusted=True)
        environ = {'REMOTE_ADDR': peer, 'REMOTE_PORT': '12345', 'SERVER_NAME': 'rihlati.me',
                   'SERVER_PORT': '8080', 'HTTP_HOST': 'rihlati.me', 'wsgi.url_scheme': 'http',
                   'HTTP_X_FORWARDED_FOR': '198.51.100.99, 192.0.2.10',
                   'HTTP_X_FORWARDED_PROTO': 'https', 'HTTP_X_FORWARDED_HOST': 'evil.example'}
        list(middleware(environ, lambda *args: None))
        return captured

    def test_client_address_extracted_from_only_last_trusted_hop(self):
        result = self.forwarded('127.0.0.1')
        self.assertEqual(result['REMOTE_ADDR'], '192.0.2.10')
        self.assertEqual(result['wsgi.url_scheme'], 'https')
        self.assertEqual(result['HTTP_HOST'], 'rihlati.me')
        self.assertNotIn('HTTP_X_FORWARDED_HOST', result)

    def test_external_or_local_demo_headers_cannot_spoof_client(self):
        for peer, trusted in [('203.0.113.10', True), ('127.0.0.1', False)]:
            result = self.forwarded(peer, trusted)
            self.assertEqual(result['REMOTE_ADDR'], peer)
            self.assertEqual(result['wsgi.url_scheme'], 'http')
            self.assertNotIn('HTTP_X_FORWARDED_FOR', result)

    def test_release_paths_exclude_private_data_and_documents(self):
        for name in ('Rihlati/data/rihlati.sqlite3', 'Rihlati/.enviroment.local',
                     'Rihlati/docs/idea.docx', 'Rihlati/docs/output/example.jpg',
                     'domin and hosting info.txt', 'rihlatiApp/www/index.html'):
            self.assertIsNotNone(path_issue(name), name)
        for name in ('README.md', 'Rihlati/.env.example', 'Rihlati/app/app.js',
                     'rihlatiApp/src/mobile.js', 'Rihlati/deploy/rihlati.service'):
            self.assertIsNone(path_issue(name), name)

    def test_secret_findings_include_only_rule_and_line(self):
        synthetic = b'sk-proj-' + b'A' * 40
        self.assertEqual(content_issues(b'example\n' + synthetic), [{'rule': 'openai-token', 'line': 2}])
        self.assertEqual(content_issues(b'OPENAI_API_KEY=\n'), [])


if __name__ == '__main__':
    unittest.main()
