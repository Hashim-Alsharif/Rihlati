"""Explicit single-host deployment settings; never trust Internet proxy headers."""
import config


def waitress_options(get=None):
    get = get or config.get
    host = get('RIHLATI_HOST', '127.0.0.1')
    production = get('RIHLATI_ENV', 'local') == 'production'
    proxy = get('RIHLATI_TRUST_PROXY', '')
    if host not in ('127.0.0.1', 'localhost'):
        raise RuntimeError('Bind Rihlati to loopback and publish it through the HTTPS reverse proxy')
    if proxy and (proxy != 'loopback' or not production or host != '127.0.0.1'):
        raise RuntimeError('Proxy trust requires production, IPv4 loopback, and RIHLATI_TRUST_PROXY=loopback')
    port = int(get('PORT', '8080'))
    if not 1 <= port <= 65535:
        raise ValueError('PORT must be between 1 and 65535')
    options = dict(host=host, port=port, threads=8,
                   max_request_body_size=80 * 1024 * 1024, channel_timeout=120,
                   expose_tracebacks=False, clear_untrusted_proxy_headers=True)
    if proxy:
        # Caddy must be the single edge proxy and overwrite client-supplied headers.
        options.update(trusted_proxy='127.0.0.1', trusted_proxy_count=1,
                       trusted_proxy_headers={'x-forwarded-for', 'x-forwarded-proto'})
    return options
