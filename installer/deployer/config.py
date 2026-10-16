import ipaddress
import re
from dataclasses import replace
from urllib.parse import urlsplit

from .models import Connection, DeployRequest

IMPORT_KEYS = frozenset({
    'FEISHU_APP_ID', 'FEISHU_APP_SECRET', 'LLM_PROVIDER', 'LLM_API_BASE_URL',
    'LLM_API_KEY', 'LLM_MODEL', 'APP_LANGUAGE', 'APP_TIMEZONE',
})
RESERVED_DIRECTORIES = frozenset({
    '/', '/etc', '/root', '/var', '/var/lib', '/var/lib/huiyang-installer',
    '/var/lib/huiyang-installer-operation-lock',
    '/home', '/opt', '/srv', '/tmp', '/usr', '/bin', '/sbin', '/dev', '/proc', '/sys', '/run',
})


def normalize_directory(value: str) -> str:
    if not isinstance(value, str) or not value.startswith('/'):
        raise ValueError('请选择服务器上的绝对目录，例如 /Lark_todo-agent。')
    if any(ord(c) < 32 or ord(c) == 127 for c in value) or len(value) > 2048:
        raise ValueError('安装路径包含无效字符或过长。')
    if any(part in ('.', '..') for part in value.split('/')):
        raise ValueError('安装路径不能包含 . 或 ..。')
    result = re.sub('/+', '/', value).rstrip('/') or '/'
    if result in RESERVED_DIRECTORIES or result.startswith(('/proc/', '/sys/', '/dev/', '/run/', '/var/lib/huiyang-installer/', '/var/lib/huiyang-installer-operation-lock/')):
        raise ValueError('请选择专门存放本项目的文件夹，不能直接使用系统目录。')
    return result


def validate_host(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError('请输入服务器 IP 或域名。')
    value = value.strip()
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        pass
    if len(value) > 253 or not value or value.startswith('-'):
        raise ValueError('服务器地址无效。')
    labels = value.rstrip('.').split('.')
    if not all(re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?', x) for x in labels):
        raise ValueError('服务器地址只需 IP 或域名，不要带协议、端口或用户名。')
    return value.rstrip('.').lower()


def validate_connection(value: Connection) -> Connection:
    host = validate_host(value.host)
    if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_.-]{0,63}', value.user):
        raise ValueError('SSH 用户名无效。')
    if not isinstance(value.port, int) or not 1 <= value.port <= 65535:
        raise ValueError('SSH 端口必须是 1 到 65535。')
    if not value.password and not value.key_path:
        raise ValueError('请输入 SSH 密码或选择私钥文件。')
    if any('\x00' in x for x in (value.password, value.passphrase, value.sudo_password)):
        raise ValueError('凭据包含无效字符。')
    return replace(value, host=host)


def parse_env(text: str, allowed: frozenset[str] | None = None) -> dict[str, str]:
    """Read single-line dotenv values without executing or interpolating anything."""
    if len(text) > 1_048_576:
        raise ValueError('配置文件超过 1 MB，无法导入。')
    values = {}
    for line in text.lstrip('\ufeff').splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if line.startswith('export '):
            line = line[7:].lstrip()
        key, sep, raw = line.partition('=')
        key = key.strip()
        if not sep or not re.fullmatch(r'[A-Z][A-Z0-9_]*', key):
            continue
        if allowed is not None and key not in allowed:
            continue
        raw = raw.strip()
        if raw.startswith(('"', "'")):
            quote = raw[0]
            end, escaped = None, False
            for i, c in enumerate(raw[1:], 1):
                if c == quote and not escaped:
                    end = i
                    break
                escaped = c == '\\' and not escaped
            if end is None or (raw[end + 1:].strip() and not raw[end + 1:].lstrip().startswith('#')):
                raise ValueError(f'{key} 的引号未正确闭合。')
            value = raw[1:end]
            if quote == '"':
                value = re.sub(r'\\([\\"$])', r'\1', value)
            else:
                value = value.replace("\\'", "'")
        else:
            value = re.split(r'\s+#', raw, maxsplit=1)[0].rstrip()
        if '\x00' in value:
            raise ValueError(f'{key} 包含无效字符。')
        values[key] = value
    return values


def import_env(text: str) -> dict[str, str]:
    return parse_env(text, IMPORT_KEYS)


def redact(text: str, secrets: list[str] | tuple[str, ...]) -> str:
    result = str(text)
    for secret in sorted({x for x in secrets if x}, key=len, reverse=True):
        result = result.replace(secret, '[REDACTED]')
    # Also mask assignments from shell/compose logs, including unknown env names.
    return re.sub(r'(?im)((?:[A-Z0-9_]*(?:SECRET|PASSWORD|TOKEN|API_KEY))\s*[=:]\s*)([^\r\n]+)', r'\1[REDACTED]', result)


def validate_deployment(request: DeployRequest, existing: dict[str, str] | None = None) -> DeployRequest:
    directory = normalize_directory(request.directory)
    host = validate_host(request.public_host)
    if request.profile.requires_feishu and not request.https:
        raise ValueError('汇漾飞书网页登录需要 HTTPS，请保持启用。')
    if not isinstance(request.port, int) or not 1024 <= request.port <= 65535:
        raise ValueError('HTTP 端口必须是 1024 到 65535。')
    if any(k not in IMPORT_KEYS for k in request.values):
        raise ValueError('配置中包含不支持的字段。')
    if any(any(ord(c) < 32 for c in str(v)) for v in request.values.values()):
        raise ValueError('配置值不能包含换行或控制字符。')
    merged = dict(existing or {})
    merged.update({k: v for k, v in request.values.items() if v})
    if request.profile.requires_feishu:
        labels = {'FEISHU_APP_ID':'App ID', 'FEISHU_APP_SECRET':'App Secret', 'LLM_API_BASE_URL':'模型 API 地址', 'LLM_API_KEY':'API Key', 'LLM_MODEL':'模型名称'}
        for key, label in labels.items():
            if not merged.get(key, '').strip():
                raise ValueError(f'请填写{label}，或先导入已有配置。')
        url = urlsplit(merged['LLM_API_BASE_URL'])
        if url.scheme != 'https' or not url.hostname or url.username or url.password or url.query or url.fragment:
            raise ValueError('模型 API 地址必须是有效的 HTTPS 地址，不能包含账号、查询参数或片段。')
        if merged.get('LLM_PROVIDER', 'openai_compatible') not in ('openai_compatible', 'deepseek'):
            raise ValueError('模型协议无效。')
        if merged.get('APP_LANGUAGE', 'zh-CN') not in ('zh-CN', 'en-US'):
            raise ValueError('汇漾默认语言无效。')
    return replace(request, directory=directory, public_host=host)
