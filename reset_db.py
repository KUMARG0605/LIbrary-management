"""
Reset the application's database files and recreate an empty schema.

This script will:
- Back up any existing sqlite files found: `library_dev.db`, `library.db`, `instance/library_dev.db`.
- Drop all tables via SQLAlchemy and re-create an empty schema.

Run locally from the project root. It is destructive — backups are created first.
"""
import os
import shutil
from datetime import datetime

BACKUP_DIR = os.path.join('backups', 'db_backups')
DB_CANDIDATES = [
    'library_dev.db',
    'library.db',
    os.path.join('instance', 'library_dev.db'),
]


def ensure_backup_dir():
    os.makedirs(BACKUP_DIR, exist_ok=True)


def backup_files():
    ensure_backup_dir()
    now = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    backed = []
    for path in DB_CANDIDATES:
        if os.path.exists(path):
            dest = os.path.join(BACKUP_DIR, f"{now}_{os.path.basename(path)}")
            shutil.copy2(path, dest)
            backed.append((path, dest))
    return backed


def reset_database():
    # Import app factory and models here to avoid importing before backup
    from app_new import create_app
    from models import db

    # Create app (development by default)
    app = create_app()

    with app.app_context():
        print('Dropping all tables...')
        db.drop_all()
        print('Creating empty schema...')
        db.create_all()


def main():
    print('Backing up database files...')
    backed = backup_files()
    if backed:
        for src, dst in backed:
            print(f'Backed up {src} -> {dst}')
    else:
        print('No database files found to back up.')

    print('Resetting database schema (this is destructive)...')
    reset_database()
    print('Database reset complete. Application now has an empty schema.')


if __name__ == '__main__':
    main()
