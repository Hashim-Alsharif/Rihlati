"""Run once on the server. Initial credentials never belong in source control."""
import getpass
import accounts
import ai_provider
import config
import knowledge

def setup(secret=None):
    knowledge.migrate(); accounts.migrate()
    with knowledge.db() as c:
        exists=c.execute('SELECT 1 FROM users WHERE is_primary=1').fetchone()
    if not exists:
        accounts.seed_primary(secret or getpass.getpass('Initial admin password (8–128 characters; uppercase A–Z, digit 0–9 and special symbol): '))
        print('Primary admin created: admin. Update contacts and password after signing in.')
    if not config.get('OPENAI_API_KEY') and ai_provider.KEY_FILE.exists():
        key=ai_provider.key()
        if key:
            config.save({'OPENAI_API_KEY':key})
            print('Existing provider key migrated to private server configuration; value not displayed.')

if __name__=='__main__':
    setup()
