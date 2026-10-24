#!/usr/bin/env python3
"""Opt-in, repeatable staff provisioning. Passwords enter only through Secrets.

Keycloak and PostgreSQL do not share a transaction: a failed run is retried,
never compensated by deleting existing accounts. No passwords/tokens are logged.
"""
import json
import os
import subprocess
import urllib.error
import urllib.parse
import urllib.request


def literal(value):
    return "'" + str(value).replace("'", "''") + "'"


class Keycloak:
    def __init__(self):
        self.base = os.environ['STAFF_SEED_KEYCLOAK_URL'].rstrip('/')
        self.realm = os.getenv('STAFF_SEED_REALM', 'staff')
        self.token = None
        data = self.call('POST', '/realms/master/protocol/openid-connect/token', form={
            'grant_type': 'password', 'client_id': 'admin-cli',
            'username': os.getenv('STAFF_SEED_ADMIN_USER', 'admin'),
            'password': os.environ['STAFF_SEED_ADMIN_PASSWORD']})
        self.token = data['access_token']

    def call(self, method, path, body=None, form=None):
        headers = {'Accept': 'application/json'}
        if self.token:
            headers['Authorization'] = 'Bearer ' + self.token
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers['Content-Type'] = 'application/json'
        if form is not None:
            data = urllib.parse.urlencode(form).encode()
            headers['Content-Type'] = 'application/x-www-form-urlencoded'
        try:
            with urllib.request.urlopen(urllib.request.Request(
                    self.base + path, method=method, headers=headers, data=data), timeout=30) as r:
                payload = r.read()
                return json.loads(payload) if payload else None
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f'Keycloak {method} failed: HTTP {exc.code}') from None

    def admin(self, method, path, body=None):
        return self.call(method, '/admin/realms/' + self.realm + '/' + path, body)

    def client(self, name):
        found = self.admin('GET', 'clients?clientId=' + urllib.parse.quote(name))
        if len(found) != 1:
            raise ValueError('Required Keycloak client missing or ambiguous: ' + name)
        return found[0]['id']

    def role(self, client, name):
        roles = self.admin('GET', f'clients/{client}/roles')
        role = next((r for r in roles if r['name'] == name), None)
        if role is None:
            self.admin('POST', f'clients/{client}/roles', {'name': name})
            role = self.admin('GET', f'clients/{client}/roles/' + urllib.parse.quote(name))
        return role


def execute_sql(prefix, statement):
    command = os.getenv('STAFF_SEED_SQL_COMMAND_JSON')
    if command:
        # Operator runner only; chart jobs normally use psycopg2 directly.
        database = os.environ[prefix + 'PGDATABASE']
        argv = [part.replace('{database}', database) for part in json.loads(command)]
        r = subprocess.run(argv, input=statement, text=True, capture_output=True)
        if r.returncode:
            raise RuntimeError('Staff seed database transaction failed')
    else:
        import psycopg2
        with psycopg2.connect(host=os.environ[prefix + 'PGHOST'],
                port=os.getenv(prefix + 'PGPORT', '5432'),
                dbname=os.environ[prefix + 'PGDATABASE'],
                user=os.environ[prefix + 'PGUSER'],
                password=os.environ[prefix + 'PGPASSWORD']) as conn:
            with conn.cursor() as cur:
                cur.execute(statement)


def iam_sql(registry, client, two_stages):
    base = ['intakeFormDefinition:view', 'intakeSubmission:view']
    read = ['register:view', 'registerDefinition:view', 'registerSection:view',
            'registerTab:view', 'registerHistory:view', 'referenceData:view']
    roles = {
        'intake': base + ['intakeSubmission:edit'],
        'l1': base + read + ['verificationIntakeForm:view',
                             'verificationIntakeForm:create'],
        'l2': base + read + (['verificationIntakeForm:view',
                              'verificationIntakeForm:create'] if two_stages else []),
    }
    statements = ['BEGIN;', 'SELECT pg_advisory_xact_lock(724196309);']
    required = sorted({p for values in roles.values() for p in values})
    names = ','.join(literal(p) for p in required)
    statements.append(f"""DO $$ BEGIN
        IF (SELECT count(*) FROM staff_portal_applications WHERE application_mnemonic={literal(client)} AND active) <> 1 THEN
          RAISE EXCEPTION 'Registry IAM application missing or ambiguous'; END IF;
        IF (SELECT count(DISTINCT p.permission_mnemonic) FROM staff_application_permissions p
          JOIN staff_portal_applications a ON a.id=p.application_id
          WHERE a.application_mnemonic={literal(client)} AND p.active AND p.permission_mnemonic IN ({names})) <> {len(required)} THEN
          RAISE EXCEPTION 'Required registry permissions missing'; END IF;
        END $$;""")
    for suffix, permissions in roles.items():
        name = registry + '.' + suffix
        statements.append(f"""DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM staff_roles r JOIN staff_portal_applications a ON a.id=r.application_id
              WHERE r.role_mnemonic={literal(name)} AND (NOT r.active OR a.application_mnemonic <> {literal(client)})) THEN
            RAISE EXCEPTION 'Existing dedicated IAM role has unexpected ownership/state'; END IF;
          END $$;""")
        statements.append(f"""INSERT INTO staff_roles
            (application_id,role_mnemonic,role_description,active,created_at,updated_at)
            SELECT id,{literal(name)},{literal('Dedicated ' + name)},true,NOW(),NOW()
            FROM staff_portal_applications WHERE application_mnemonic={literal(client)}
            AND NOT EXISTS (SELECT 1 FROM staff_roles WHERE role_mnemonic={literal(name)}) ;""")
        # Stage authority is checked by AWE task assignment. This legacy grant
        # calls approve_submission directly and can bypass the staged workflow.
        # Remove it only from the dedicated roles managed by this provisioner.
        statements.append(f"""DELETE FROM staff_role_permissions rp
            USING staff_roles r, staff_application_permissions p
            WHERE rp.role_id=r.id AND rp.permission_id=p.id
              AND r.role_mnemonic={literal(name)}
              AND p.permission_mnemonic='intakeSubmission:approve';""")
        for permission in permissions:
            statements.append(f"""INSERT INTO staff_role_permissions
                (role_id,permission_id,active,created_at,updated_at)
                SELECT r.id,p.id,true,NOW(),NOW()
                FROM staff_roles r JOIN staff_application_permissions p ON p.application_id=r.application_id
                WHERE r.role_mnemonic={literal(name)} AND p.permission_mnemonic={literal(permission)} AND p.active
                AND NOT EXISTS (SELECT 1 FROM staff_role_permissions x WHERE x.role_id=r.id AND x.permission_id=p.id);""")
    statements.append('COMMIT;')
    return '\n'.join(statements)


def awe_sql(registry, policies):
    # Only future stage assignments change. Existing task assignees/history stay intact.
    # Each existing rule id/mode/stage survives; no stage is added or retired.
    targets = ','.join(literal(p) for p in policies)
    statement = f"""BEGIN;
        SELECT pg_advisory_xact_lock(724196309);
        UPDATE approver_rule r SET rule_type='user',
          rule_value=json_build_object('user_id', {literal(registry)} || '.l' ||
             CASE WHEN s.stage_order=2 THEN '2' ELSE '1' END), updated_at=NOW()
        FROM approval_stage s JOIN approval_policy p ON p.id=s.policy_id
        WHERE r.stage_id=s.id AND p.policy_key IN ({targets})
          AND (s.skip_if IS NULL OR s.skip_if::text='null')
          AND (r.rule_type='http' OR COALESCE(r.rule_value->>'user_id','') <> 'admin'
               OR {literal(registry)}='cropsown')
          AND (r.rule_type <> 'user' OR r.rule_value->>'user_id' IS DISTINCT FROM
             {literal(registry)} || '.l' || CASE WHEN s.stage_order=2 THEN '2' ELSE '1' END);
        COMMIT;"""
    return statement


def main():
    if os.getenv('STAFF_SEED_ENABLED', 'false').lower() != 'true':
        print('[staff-seed] disabled')
        return
    registry = os.environ['STAFF_SEED_REGISTRY']
    if registry not in ('farmer', 'livestock', 'cropsown'):
        raise ValueError('Unsupported registry')
    policies = json.loads(os.environ['STAFF_SEED_POLICY_KEYS'])
    if not policies or not all(p.startswith('registry.intake_form.') for p in policies):
        raise ValueError('Explicit intake policy keys required')
    two_stages = os.environ['STAFF_SEED_TWO_STAGES'].lower() == 'true'
    targets = ','.join(literal(p) for p in policies)
    execute_sql('AWE_', f"""DO $$ BEGIN
      IF (SELECT count(DISTINCT policy_key) FROM approval_policy WHERE policy_key IN ({targets})) <> {len(policies)} THEN
        RAISE EXCEPTION 'Required approval policies missing'; END IF;
      IF EXISTS (SELECT 1 FROM approval_stage s JOIN approval_policy p ON p.id=s.policy_id
          WHERE p.policy_key IN ({targets}) AND (s.skip_if IS NULL OR s.skip_if::text='null')
          AND s.stage_order > {2 if two_stages else 1}) THEN
        RAISE EXCEPTION 'Unexpected approval stage topology'; END IF;
      IF EXISTS (SELECT 1 FROM approval_policy p LEFT JOIN approval_stage s
          ON s.policy_id=p.id AND (s.skip_if IS NULL OR s.skip_if::text='null') WHERE p.policy_key IN ({targets})
          GROUP BY p.id HAVING count(s.id) <> {2 if two_stages else 1}) THEN
        RAISE EXCEPTION 'Missing or unexpected active approval stages'; END IF;
      IF EXISTS (SELECT 1 FROM approval_stage s JOIN approval_policy p ON p.id=s.policy_id
          WHERE p.policy_key IN ({targets}) AND (s.skip_if IS NULL OR s.skip_if::text='null')
          AND NOT EXISTS (SELECT 1 FROM approver_rule r WHERE r.stage_id=s.id)) THEN
        RAISE EXCEPTION 'Active approval stage has no approver rule'; END IF;
      END $$;""")
    # All inputs validated before creating anything. New passwords are required
    # even on rerun, but are used ONLY for new users, never to reset an existing one.
    passwords = {s: os.environ['STAFF_SEED_PASSWORD_' + s.upper()] for s in ('intake', 'l1', 'l2')}
    if any(len(p) < 16 for p in passwords.values()) or len(set(passwords.values())) != 3:
        raise ValueError('Three distinct passwords of at least 16 characters required')
    kc = Keycloak()
    client_name = os.environ['STAFF_SEED_CLIENT_ID']
    client = kc.client(client_name)
    dashboard = kc.client(os.environ['STAFF_SEED_DASHBOARD_CLIENT_ID'])
    viewer = next((r for r in kc.admin('GET', f'clients/{dashboard}/roles')
                   if r['name'] == 'Dashboard Viewer'), None)
    if viewer is None:
        raise ValueError('Dashboard Viewer role must exist before staff seed')
    execute_sql('IAM_', iam_sql(registry, client_name, two_stages))
    for suffix in ('intake', 'l1', 'l2'):
        name = registry + '.' + suffix
        users = kc.admin('GET', 'users?exact=true&username=' + urllib.parse.quote(name))
        role = kc.role(client, name)
        if not users:
            kc.admin('POST', 'users', {'username': name, 'enabled': True,
                'firstName': registry.capitalize(), 'lastName': suffix.upper(),
                'email': name + '@' + os.getenv('STAFF_SEED_EMAIL_DOMAIN', 'example.invalid'),
                'requiredActions': [],
                'credentials': [{'type': 'password', 'value': passwords[suffix], 'temporary': False}]})
            users = kc.admin('GET', 'users?exact=true&username=' + urllib.parse.quote(name))
        if len(users) != 1 or not users[0].get('enabled'):
            raise ValueError('Existing account missing, ambiguous or disabled: ' + name)
        user = users[0]
        # Dedicated development role accounts have non-deliverable profile
        # addresses, not invented staff contacts. Preserve any populated email.
        if not user.get('email'):
            kc.admin('PUT', f"users/{user['id']}", {
                'email': name + '@' + os.getenv('STAFF_SEED_EMAIL_DOMAIN', 'example.invalid')})
        current = kc.admin('GET', f"users/{user['id']}/role-mappings")
        # Refuse unexpected privileges rather than silently modifying an existing person.
        allowed = {(client_name, name)}
        if suffix == 'l2':
            allowed.add((os.environ['STAFF_SEED_DASHBOARD_CLIENT_ID'], 'Dashboard Viewer'))
        for mapping in current.get('clientMappings', {}).values():
            if mapping['client'] == 'account':
                continue
            if any((mapping['client'], r['name']) not in allowed for r in mapping['mappings']):
                raise ValueError('Unexpected existing grants: ' + name)
        kc.admin('POST', f"users/{user['id']}/role-mappings/clients/{client}", [role])
        if suffix == 'l2':
            kc.admin('POST', f"users/{user['id']}/role-mappings/clients/{dashboard}", [viewer])
        print('[staff-seed] ready ' + name)
    execute_sql('AWE_', awe_sql(registry, policies))
    print('[staff-seed] complete ' + registry)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        # Avoid SQL, request bodies or credential-bearing URLs in errors.
        print('[staff-seed] FAILED ' + type(exc).__name__)
        raise SystemExit(1)
