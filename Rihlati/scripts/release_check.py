"""Read-only repository guard; reports locations/rules, never secret values.

Run before staging, then with --staged before committing. A basic pattern/path
check, not an independent security or copyright audit. Ignored files are not read.
"""
import argparse
import json
from pathlib import Path, PurePosixPath
import re
import subprocess

REPO = Path(__file__).resolve().parents[2]
ROOT_FILES = {'README.md', 'AGENTS.md', '.gitignore'}
PRIVATE_PARTS = {'.git', '.venv', 'node_modules', 'data', 'references', 'uploads',
                 'www', 'dist', 'artifacts', '.gradle', '__pycache__', 'Pods',
                 'xcuserdata', '.build', 'build'}
PRIVATE_SUFFIXES = {'.pdf', '.doc', '.docx', '.ppt', '.pptx', '.zip', '.7z',
                    '.sqlite', '.db', '.pem', '.key', '.p12', '.jks', '.keystore',
                    '.mobileprovision', '.mp3', '.wav', '.webm', '.m4a', '.log'}
PATTERNS = {
    'openai-token': re.compile(rb'\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{24,}'),
    'github-token': re.compile(rb'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})'),
    'private-key': re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----'),
    'aws-access-key': re.compile(rb'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b'),
    'credential-url': re.compile(rb'https?://[^\s/@:]+:[^\s/@]+@'),
}


def path_issue(name):
    path = PurePosixPath(name)
    if len(path.parts) == 1:
        return None if name in ROOT_FILES else 'unapproved-root-file'
    if path.parts[0] not in {'Rihlati', 'rihlatiApp'} or '..' in path.parts:
        return 'outside-projects'
    if any(part in PRIVATE_PARTS for part in path.parts):
        return 'private-or-generated-directory'
    if name.startswith(('Rihlati/docs/archive/', 'Rihlati/docs/output/', 'Rihlati/docs/tmp/')):
        return 'private-document-output'
    if path.name.startswith('.env') and path.name != '.env.example':
        return 'environment-secret-file'
    if path.suffix.lower() in PRIVATE_SUFFIXES or '.sqlite3' in path.name or path.name.endswith('.local'):
        return 'private-or-unreviewed-artifact'
    return None


def content_issues(data):
    return [dict(rule=rule, line=data.count(b'\n', 0, match.start()) + 1)
            for rule, pattern in PATTERNS.items() for match in pattern.finditer(data)]


def git(*args):
    return subprocess.check_output(['git', '-C', str(REPO), *args])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--staged', action='store_true', help='Check index contents, not working tree contents')
    args = parser.parse_args()
    listing = ['ls-files', '-z', '--cached']
    if not args.staged:
        listing += ['--others', '--exclude-standard']
    names = sorted(set(git(*listing).decode('utf-8').split('\0')) - {''})
    findings = []
    for name in names:
        issue = path_issue(name)
        if issue:
            findings.append(dict(path=name, rule=issue))
            continue  # Do not inspect private contents even if staged accidentally.
        path = REPO / name
        if path.is_symlink() or (args.staged and git('ls-files', '-s', '--', name).startswith(b'120000')):
            findings.append(dict(path=name, rule='symlink-requires-review'))
            continue
        try:
            data = git('show', ':' + name) if args.staged else path.read_bytes()
        except (OSError, subprocess.CalledProcessError):
            findings.append(dict(path=name, rule='unreadable-file'))
            continue
        if len(data) > 20 * 1024 * 1024:
            findings.append(dict(path=name, rule='large-file-requires-review'))
        findings.extend(dict(path=name, **issue) for issue in content_issues(data))
    print(json.dumps(dict(mode='index' if args.staged else 'working-tree',
                          files_checked=len(names), findings=findings), ensure_ascii=True, indent=2))
    return 1 if findings or not names else 0


if __name__ == '__main__':
    raise SystemExit(main())
