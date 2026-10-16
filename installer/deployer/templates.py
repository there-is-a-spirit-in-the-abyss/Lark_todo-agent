"""Pure configuration builders; returned files are private on the server."""
from __future__ import annotations

import ipaddress
import json
import secrets

from .models import DeployRequest

GATEWAY_ROOT = '/var/lib/huiyang-installer'
GATEWAY_NETWORK = 'huiyang-installer-gateway'
GATEWAY_IMAGE = 'caddy:2.11.6-alpine@sha256:d44355d3c2149dc580ce2cac735955d1c08d3d00882c30489c241aa51a5c10d9'


def environment(request: DeployRequest, existing=None) -> dict[str, str]:
    result = dict(existing or {})
    result.update({key: value for key, value in request.values.items() if value})
    if request.profile.requires_feishu:
        result.setdefault('POSTGRES_PASSWORD', secrets.token_hex(32))
        result.update(APP_ENV='production', PLATFORM_ENABLED='true', FEISHU_EVENT_MODE='long_connection',
                      TEAM_WEB_ENABLED='true', TEAM_PUBLIC_URL=request.origin,
                      TEAM_STATIC_DIR='/root/huiyang/web/dist')
        result.setdefault('LLM_PROVIDER', 'openai_compatible')
        result.setdefault('APP_LANGUAGE', 'zh-CN')
        result.setdefault('APP_TIMEZONE', 'UTC')
    else:
        result.update(PUBLIC_URL=request.origin, DATABASE_PATH='/app/data/team-todo.db', STATIC_DIR='/app/web/dist')
    return result


def dotenv(values: dict[str, str]) -> bytes:
    def quote(value):
        if any(ord(c) < 32 for c in value):
            raise ValueError('配置值包含控制字符，无法安全写入。')
        # Compose expands double-quoted values. Escaped dollars remain literal;
        # use this form so even a trailing backslash round-trips correctly.
        return '"' + value.replace('\\', '\\\\').replace('"', '\\"').replace('$', '\\$') + '"'
    return ('\n'.join(f'{key}={quote(str(value))}' for key, value in sorted(values.items())) + '\n').encode('utf-8')


def json_bytes(document: dict) -> bytes:
    return (json.dumps(document, ensure_ascii=False, indent=2) + '\n').encode('utf-8')


def compose_document(request: DeployRequest, image: str, alias: str) -> dict:
    app = {'image': image, 'restart':'unless-stopped', 'env_file':['.env'],
           'healthcheck': {'test':['CMD','python','-c',"import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=5)"], 'interval':'5s','timeout':'8s','retries':30,'start_period':'20s'}}
    services = {'app':app}
    if request.profile.requires_feishu:
        app['environment'] = {'DATABASE_URL':'postgresql+asyncpg://huiyang:${POSTGRES_PASSWORD:?required}@db:5432/huiyang', 'ENV_PATH':'/root/huiyang/.env'}
        app['volumes'] = ['./.env:/root/huiyang/.env:ro']
        app['depends_on'] = {'db':{'condition':'service_healthy'}}
        services['db'] = {'image':'postgres:16-alpine','restart':'unless-stopped',
                          'environment':{'POSTGRES_DB':'huiyang','POSTGRES_USER':'huiyang','POSTGRES_PASSWORD':'${POSTGRES_PASSWORD:?required}'},
                          'healthcheck':{'test':['CMD-SHELL','pg_isready -U huiyang -d huiyang'],'interval':'3s','timeout':'5s','retries':30},
                          'volumes':['./postgres_data:/var/lib/postgresql/data']}
    else:
        app['volumes'] = ['./data:/app/data']
    doc = {'services':services}
    if request.https:
        app['networks'] = {'default':{}, 'gateway':{'aliases':[alias]}}
        doc['networks'] = {'gateway':{'external':True,'name':GATEWAY_NETWORK}}
    else:
        app['ports'] = [f'{request.port}:8000']
    return doc


def gateway_document(routes: list[dict]) -> dict:
    grouped = {}
    for route in routes:
        grouped.setdefault(route['host'], []).append(route)
    http_routes, policies = [], []
    for host, entries in sorted(grouped.items()):
        handlers = []
        for entry in sorted(entries, key=lambda x: x['profile'] != 'huiyang'):
            handler = {'handle':[{'handler':'reverse_proxy','upstreams':[{'dial':entry['alias'] + ':8000'}]}], 'terminal':True}
            if entry['profile'] == 'huiyang':
                handler['match'] = [{'path':['/team','/team/*','/api/team','/api/team/*']}]
            handlers.append(handler)
        http_routes.append({'match':[{'host':[host]}], 'handle':[{'handler':'subroute','routes':handlers}], 'terminal':True})
        issuer = {'module':'acme','ca':'https://acme-v02.api.letsencrypt.org/directory'}
        try:
            ipaddress.ip_address(host)
            issuer['profile'] = 'shortlived'
        except ValueError:
            pass
        policies.append({'subjects':[host], 'issuers':[issuer]})
    return {'apps':{'http':{'servers':{'public':{'listen':[':443'],'routes':http_routes}}},
                    'tls':{'automation':{'policies':policies}}}}


def gateway_compose() -> dict:
    return {'services':{'gateway':{'image':GATEWAY_IMAGE,'restart':'unless-stopped',
            'labels':{'io.huiyang.installer.owner':'huiyang-installer'},
            'command':['caddy','run','--config','/etc/caddy/caddy.json'],
            'ports':['80:80','443:443','443:443/udp'],
            'volumes':['./config:/etc/caddy:ro','./data:/data','./runtime:/config'],
            'networks':['gateway']}},'networks':{'gateway':{'external':True,'name':GATEWAY_NETWORK}}}
