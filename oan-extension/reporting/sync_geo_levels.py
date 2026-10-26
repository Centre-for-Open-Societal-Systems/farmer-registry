"""Publish reporting level labels from the supported Master Data HTTP API.

No Master Data DB access, registered-person inference or country-level fallback.
"""
import json
import os
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import uuid4


class GeographyUnavailable(RuntimeError):
    pass


def post(url, body, *, token=None, form=False):
    headers = {'Content-Type':'application/x-www-form-urlencoded' if form else 'application/json'}
    if token:
        headers['Authorization'] = 'Bearer '+token
    data = urlencode(body).encode() if form else json.dumps(body).encode()
    try:
        with urlopen(Request(url,data=data,headers=headers,method='POST'),timeout=30) as response:
            return json.load(response)
    except Exception:
        raise GeographyUnavailable('Master Data reporting geography unavailable; previous labels retained') from None


def ordered_levels(levels):
    if not isinstance(levels,list) or not levels:
        raise GeographyUnavailable('Master Data supplied no reporting geography levels')
    if any(not isinstance(level,dict) or not level.get('level_id') for level in levels):
        raise GeographyUnavailable('Master Data geography has missing level IDs')
    by_id = {level['level_id']:level for level in levels}
    if len(by_id) != len(levels):
        raise GeographyUnavailable('Master Data geography has duplicate level IDs')
    ordered, parent = [], None
    while len(ordered) < len(levels):
        children = [level for level in levels if (level.get('parent_level_id') or None) == parent]
        if len(children) != 1:
            raise GeographyUnavailable('Master Data geography is not one connected ordered hierarchy')
        level = children[0]
        if level['level_id'] in {row['level_id'] for row in ordered} or not level.get('level_mnemonic'):
            raise GeographyUnavailable('Master Data geography has cyclic or unnamed levels')
        ordered.append(level)
        parent = level['level_id']
    if len(ordered) > 5:
        raise GeographyUnavailable('Reporting supports five geography positions; extend reporting before enabling this pack')
    return [(index,level['level_mnemonic']) for index,level in enumerate(ordered,start=1)]


def fetch_levels(api_url,token_url,client_id,client_secret):
    # Native client-credentials and request-envelope contracts, independently
    # scoped to read-only Master Data roles. Missing authentication fails closed.
    if not all((api_url,token_url,client_id,client_secret)):
        raise GeographyUnavailable('Configure Master Data reporting API and service-account Secret')
    token = post(token_url,{'grant_type':'client_credentials','client_id':client_id,'client_secret':client_secret},form=True).get('access_token')
    if not token:
        raise GeographyUnavailable('Master Data reporting authentication refused')
    body = post(api_url.rstrip('/')+'/geo/get_all_geo_levels',{
        'request_header':{'sender_app_mnemonic':'oan-farmer-reporting','sender_app_url':'',
            'request_id':uuid4().hex,'request_timestamp':datetime.now(timezone.utc).isoformat()},
        'request_body':{'pagination_request':None,'request_payload':{}}},token=token)
    if str((body.get('response_header') or {}).get('response_status') or '').upper() != 'SUCCESS':
        raise GeographyUnavailable('Master Data refused reporting geography lookup')
    return ordered_levels((body.get('response_body') or {}).get('response_payload'))


def main():
    import psycopg2
    from psycopg2 import sql
    levels = fetch_levels(*(os.environ.get(name,'') for name in
        ('MDS_API_URL','MDS_TOKEN_URL','MDS_CLIENT_ID','MDS_CLIENT_SECRET')))
    # Registry PG* settings only. Value parameters are quoted as SQL literals;
    # replacing the view keeps its existing owner and reader privileges.
    values = sql.SQL(',').join(sql.SQL('({}, {})').format(sql.Literal(depth),sql.Literal(name)) for depth,name in levels)
    with psycopg2.connect('') as connection, connection.cursor() as cursor:
        cursor.execute(sql.SQL('CREATE OR REPLACE VIEW fr_rpt_geo_levels AS SELECT * FROM (VALUES {}) AS geo(depth,level_name)').format(values))
    print('PASS: reporting geography labels synchronized through Master Data API')


if __name__ == '__main__':
    try:
        main()
    except GeographyUnavailable as error:
        raise SystemExit(str(error)) from None
