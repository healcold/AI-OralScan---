"""Provision patient and administrator accounts from the command line."""
import argparse
from getpass import getpass
import re

from sqlalchemy.exc import IntegrityError

from .auth import create_account
from .config import get_settings
from .database import SessionLocal, engine, initialize_schema


def main():
    parser = argparse.ArgumentParser(description='Create an OralScan account')
    parser.add_argument('username', help='3–64 letters, digits, dots, dashes or underscores')
    parser.add_argument('--admin', action='store_true', help='Allow model management (no access to other accounts’ checks)')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{2,63}', args.username):
        parser.error('Invalid username')
    password = getpass('Password (12–128 characters): ')
    if not 12 <= len(password) <= 128:
        parser.error('Password must be 12–128 characters')
    if password != getpass('Confirm password: '):
        parser.error('Passwords do not match')
    database_url = get_settings().database_url
    if database_url.startswith('sqlite:///') and database_url != 'sqlite:///:memory:':
        from pathlib import Path
        Path(database_url.removeprefix('sqlite:///')).parent.mkdir(parents=True, exist_ok=True)
    initialize_schema(engine)
    with SessionLocal() as db:
        try:
            account = create_account(db, args.username, password, 'admin' if args.admin else 'patient')
        except IntegrityError:
            parser.error('Username already exists')
        print(f'Created {account.username} ({account.role})')


if __name__ == '__main__':
    main()
