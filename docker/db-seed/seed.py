"""Transactional COSS metadata seed; shared lookup catalogs are managed by MDS."""
import os
import re
from pathlib import Path
import subprocess
import sys

import psycopg2

ROOT = Path('/seed')


def enabled(name):
    return os.getenv(name, 'false').lower() == 'true'


def connect(prefix=''):
    return psycopg2.connect(**{
        'host': os.environ[prefix + 'PGHOST'],
        'port': os.getenv(prefix + 'PGPORT', '5432'),
        'dbname': os.environ[prefix + 'PGDATABASE'],
        'user': os.environ[prefix + 'PGUSER'],
        'password': os.environ[prefix + 'PGPASSWORD'],
    })


def apply(conn, files, callback=False):
    # All SQL for this database commits together or rolls back together.
    with conn:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(724196308)")
            for path in files:
                text = path.read_text(encoding='utf-8')
                if not re.sub(r'--[^\n]*|/\*.*?\*/', '', text, flags=re.S).strip():
                    continue
                if path.suffix == '.tpl':
                    if not callback:
                        raise ValueError('Unexpected SQL template')
                    for key in ('AWE_CALLBACK_SECRET_ID', 'AWE_CALLBACK_CALLER_SERVICE',
                                'AWE_CALLBACK_HMAC_SECRET'):
                        value = os.environ[key]
                        if not value:
                            raise ValueError('Missing callback configuration')
                        text = text.replace("'${" + key + "}'", cur.mogrify('%s', (value,)).decode())
                print(f'[db-seed] Applying {path.parent.name}/{path.name}', flush=True)
                cur.execute(text)


def main():
    # These flags would mutate shared catalogs or create fixtures in an existing
    # installation. Keep those operations in their explicit operator workflows.
    if any(enabled(k) for k in ('LOAD_GEO_DATA', 'LOAD_SAMPLE_DATA', 'LOAD_IMAGES')):
        raise ValueError('Use the explicit data migration workflow for geography/sample/images')
    files = [p for p in sorted((ROOT / 'meta_data').rglob('*.sql'))
             if 'lookup-data' not in p.parts]
    if not files:
        raise ValueError('Registry metadata is missing')
    conn = connect()
    try:
        apply(conn, files)
    finally:
        conn.close()
    print('[db-seed] Registry metadata committed; shared MDS lookups were not modified.', flush=True)
    if enabled('AWE_DB_SEED_ENABLED'):
        conn = connect('AWE_')
        try:
            apply(conn, sorted((ROOT / 'awe_meta_data').glob('*.sql')) +
                  sorted((ROOT / 'awe_meta_data').glob('*.tpl')), callback=True)
        finally:
            conn.close()
        print('[db-seed] AWE metadata committed.', flush=True)
    for flag, script in [('SYNC_GEO_WIDGETS', 'sync_geo_widgets.py'),
                         ('LOAD_TEMPLATES', 'upload_templates.py')]:
        if enabled(flag):
            subprocess.run([sys.executable, str(ROOT / script)], check=True)
    print('[db-seed] All enabled seed stages completed.', flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        # PostgreSQL exceptions can include SQL rows, credentials and personal
        # data. The preceding filename and SQLSTATE locate the failure safely.
        print(f'[db-seed] FAILED: {type(exc).__name__}; SQLSTATE={getattr(exc, "pgcode", None) or "n/a"}',
              file=sys.stderr)
        sys.exit(1)
