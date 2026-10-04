"""Create a consistent, timestamped SQLite backup. Never overwrite a backup."""
from datetime import datetime, timezone
import sqlite3
from knowledge import ROOT, db

def main():
    folder=ROOT/'data/backups';folder.mkdir(parents=True,exist_ok=True)
    target=folder/('rihlati-'+datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f')+'.sqlite3')
    with db() as source:
        backup=sqlite3.connect(target)
        try:source.backup(backup)
        finally:backup.close()
    print('Backup created: '+str(target.relative_to(ROOT)))

if __name__=='__main__':main()
