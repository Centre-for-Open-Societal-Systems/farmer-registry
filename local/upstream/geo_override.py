"""Install the versioned COSS geography and migrate trial references in place.

Run with trial registry writers stopped. Preflight both databases before writes;
keep a recovery journal before committing either database. No user records are deleted.
"""
import gzip
import hashlib
import json
import os
from pathlib import Path
import re

import psycopg2
from psycopg2 import sql
from psycopg2.extras import Json, RealDictCursor

SOURCE = Path('/trial/geo/ethiopia_geo_seed.sql.gz')
JOURNAL = Path('/trial/state/geo-migration-recovery.json')
VERSION = 'coss-ethiopia-four-levels-v1'


def connect(database):
    return psycopg2.connect(host=os.environ['PGHOST'], port=os.getenv('PGPORT', '5432'),
        user=os.environ['PGUSER'], password=os.environ['PGPASSWORD'], dbname=database)


def hierarchy(value_id, values, levels):
    rows = []
    while value_id:
        value = values[value_id]
        level = levels[value['level_id']]
        rows.append(dict(level=level['level_mnemonic'], level_id=level['level_id'],
            level_mnemonic=level['level_mnemonic'], level_value_id=value_id,
            level_value_mnemonic=value['level_value_mnemonic']))
        value_id = value['parent_level_value_id']
    return dict(lowest_level_value_id=rows[0]['level_value_id'], hierarchy=list(reversed(rows)))


def main():
    if os.environ['PGDATABASE'] != 'farmer_registry_db' or os.environ['MD_PGDATABASE'] != 'farmer_master_data_db':
        raise RuntimeError('This installer is restricted to the local Farmer trial databases')
    digest = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    md, registry = connect(os.environ['MD_PGDATABASE']), connect(os.environ['PGDATABASE'])
    try:
        m = md.cursor(cursor_factory=RealDictCursor)
        r = registry.cursor(cursor_factory=RealDictCursor)
        m.execute('CREATE TABLE IF NOT EXISTS coss_geo_migrations (version text PRIMARY KEY, sha256 text NOT NULL)')
        m.execute('SELECT sha256 FROM coss_geo_migrations WHERE version=%s', (VERSION,))
        applied = m.fetchone()
        if applied:
            if applied['sha256'] != digest:
                raise RuntimeError('Applied geography changed; add a new versioned migration')
            if JOURNAL.exists():
                raise RuntimeError('Incomplete cross-database migration: inspect the recovery journal before continuing')
            print('COSS geography already installed; unchanged', flush=True)
            md.rollback()
            return
        if JOURNAL.exists():
            raise RuntimeError('A recovery journal exists; reconcile the previous migration first')
        for table, key in [('g2p_geo_levels', 'level_id'), ('g2p_geo_level_values', 'level_value_id')]:
            m.execute(sql.SQL('CREATE TEMP TABLE {} (LIKE {} INCLUDING DEFAULTS)').format(sql.Identifier('new_' + table), sql.Identifier(table)))
            m.execute(sql.SQL('ALTER TABLE {} ADD PRIMARY KEY ({})').format(sql.Identifier('new_' + table), sql.Identifier(key)))
        # The exported catalog has additional optional columns absent in MDS rc.104.
        source = gzip.decompress(SOURCE.read_bytes()).decode('utf-8')
        for table, columns in [('g2p_geo_levels', ['display_name','display_name_i18n','version','valid_from','valid_to']),
            ('g2p_geo_level_values', ['pcode','pcode_source','boundary_uri','boundary_simplified_uri','display_name','display_name_i18n','version','valid_from','valid_to'])]:
            for column in columns:
                m.execute(sql.SQL('ALTER TABLE {} ADD COLUMN IF NOT EXISTS {} text').format(sql.Identifier('new_' + table), sql.Identifier(column)))
            source = source.replace('public.' + table, 'pg_temp.new_' + table)
        source = re.sub(r'^\s*(BEGIN|COMMIT);\s*$', '', source, flags=re.M)
        m.execute(source)
        # RC MDS requires unique labels within one parent. The source includes
        # distinct Kebeles with the same name; retain both IDs and disambiguate
        # their displayed labels with their P-codes instead of dropping places.
        m.execute('''UPDATE new_g2p_geo_level_values v
            SET level_value_mnemonic=v.level_value_mnemonic || ' (' || split_part(v.level_value_id,'-',2) || ')'
            FROM (SELECT level_id,parent_level_value_id,level_value_mnemonic
                  FROM new_g2p_geo_level_values GROUP BY 1,2,3 HAVING count(*)>1) d
            WHERE v.level_id=d.level_id AND v.parent_level_value_id IS NOT DISTINCT FROM d.parent_level_value_id
              AND v.level_value_mnemonic=d.level_value_mnemonic''')
        m.execute('SELECT * FROM new_g2p_geo_levels')
        levels = {v['level_id']: dict(v) for v in m.fetchall()}
        m.execute('SELECT * FROM new_g2p_geo_level_values')
        values = {v['level_value_id']: dict(v) for v in m.fetchall()}
        if {v['level_mnemonic'] for v in levels.values()} != {'region','zone','woreda','kebele'}:
            raise RuntimeError('Expected Region > Zone > Woreda > Kebele')
        expected = {'region': None, 'zone': 'region', 'woreda': 'zone', 'kebele': 'woreda'}
        for level in levels.values():
            parent = levels.get(level['parent_level_id'])
            if (parent['level_mnemonic'] if parent else None) != expected[level['level_mnemonic']]:
                raise RuntimeError('Invalid level parent: ' + str(level))
        for value in values.values():
            parent = values.get(value['parent_level_value_id'])
            if value['level_id'] not in levels or (parent['level_id'] if parent else None) != levels[value['level_id']]['parent_level_id']:
                raise RuntimeError('Invalid value parent: ' + value['level_value_id'])
        m.execute('SELECT * FROM g2p_geo_levels')
        old_levels = [dict(v) for v in m.fetchall()]
        m.execute('SELECT * FROM g2p_geo_level_values')
        old_values = [dict(v) for v in m.fetchall()]
        level_names = {v['level_id']: v['level_mnemonic'] for v in old_levels}
        mapping = {key: key for key in values}
        for value in old_values:
            level = level_names[value['level_id']]
            old_id = value['level_value_id']
            code = value.get('pcode') or old_id.removeprefix(level + '-')
            target = level + '-' + code
            if target in values:
                mapping[old_id] = target
        r.execute("SELECT table_name FROM information_schema.columns WHERE table_schema='public' AND column_name='geo_lowest_level_value_id' ORDER BY table_name")
        changes = []
        for row in r.fetchall():
            table = row['table_name']
            r.execute(sql.SQL('LOCK TABLE {} IN SHARE ROW EXCLUSIVE MODE').format(sql.Identifier(table)))
            r.execute(sql.SQL('SELECT ctid::text AS row_id, geo_lowest_level_value_id AS value, geo_code_hierarchy_json AS hierarchy FROM {} WHERE geo_lowest_level_value_id IS NOT NULL OR geo_code_hierarchy_json IS NOT NULL').format(sql.Identifier(table)))
            for record in r.fetchall():
                old_id = record['value'] or (record['hierarchy'] or {}).get('lowest_level_value_id')
                if not old_id:
                    if not record['hierarchy']:
                        continue
                    raise RuntimeError(f'{table} has hierarchy without a lowest-level ID: {record["row_id"]}')
                if old_id not in mapping:
                    raise RuntimeError(f'Cannot map {table} location {old_id}; no records changed')
                target = mapping[old_id]
                new_hierarchy = dict(record['hierarchy'] or {})
                new_hierarchy.update(hierarchy(target, values, levels))
                changes.append(dict(table=table, **record, target=target, new_hierarchy=new_hierarchy))
        print(f'Validated {len(levels)} levels, {len(values)} places; mapping {len(changes)} record locations', flush=True)
        # Durable journal allows reconciliation if the process dies between commits.
        JOURNAL.parent.mkdir(parents=True, exist_ok=True)
        JOURNAL.write_text(json.dumps(dict(version=VERSION, levels=old_levels, values=old_values, records=changes), default=str), encoding='utf-8')
        m.execute('LOCK TABLE g2p_geo_levels, g2p_geo_level_values IN ACCESS EXCLUSIVE MODE')
        m.execute('DELETE FROM g2p_geo_level_values; DELETE FROM g2p_geo_levels')
        for table in ['g2p_geo_levels', 'g2p_geo_level_values']:
            m.execute('SELECT column_name FROM information_schema.columns WHERE table_schema=%s AND table_name=%s ORDER BY ordinal_position', ('public', table))
            columns = sql.SQL(',').join(sql.Identifier(v['column_name']) for v in m.fetchall())
            m.execute(sql.SQL('INSERT INTO {} ({}) SELECT {} FROM {}').format(sql.Identifier(table), columns, columns, sql.Identifier('new_' + table)))
        for change in changes:
            r.execute(sql.SQL('UPDATE {} SET geo_lowest_level_value_id=%s,geo_code_hierarchy_json=%s WHERE ctid=%s::tid').format(sql.Identifier(change['table'])),
                (change['target'], Json(change['new_hierarchy']), change['row_id']))
        m.execute('INSERT INTO coss_geo_migrations VALUES (%s,%s)', (VERSION, digest))
        md.commit()
        registry.commit()
        JOURNAL.unlink()
        print('COSS geography installed; existing records preserved', flush=True)
    except Exception:
        md.rollback()
        registry.rollback()
        raise
    finally:
        md.close()
        registry.close()


if __name__ == '__main__':
    main()
