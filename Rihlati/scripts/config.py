"""Portable, server-only settings. Never serve the project directory."""
import os
import threading
from pathlib import Path
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
# Production may keep the editable secret file in its private writable directory,
# leaving application code read-only for the service account.
ENV_FILE = Path(os.environ.get('RIHLATI_ENV_FILE', ROOT / '.enviroment.local'))
LOCK = threading.RLock()

def get(name, default=''):
    # Explicit process environment is useful for managed production secrets.
    return os.environ.get(name, dotenv_values(ENV_FILE).get(name, default)) or default

def save(values):
    with LOCK:
        current = dict(dotenv_values(ENV_FILE))
        for key, value in values.items():
            if value is None:
                current.pop(key, None)
            else:
                current[key] = str(value)
        content = ''.join(f"{k}='{str(v or '').replace(chr(92), chr(92)*2).replace(chr(39), chr(92)+chr(39))}'\n" for k,v in current.items())
        temporary = ENV_FILE.with_suffix('.local.tmp')
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            stream.write(content)
        os.replace(temporary, ENV_FILE)
        os.chmod(ENV_FILE, 0o600)
