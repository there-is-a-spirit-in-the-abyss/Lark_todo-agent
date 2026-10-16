import hashlib
import json
import re
import sys
from pathlib import Path

from .models import Bundle, get_profile


def resource_root() -> Path:
    return Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))


def load_bundle(directory: Path | None = None) -> Bundle:
    directory = directory or resource_root() / 'bundle'
    try:
        manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        raise ValueError('安装包缺少部署资源；开发者请先运行 installer/build.py --bundle-only。') from None
    profile = get_profile(manifest.get('project', ''))
    image = manifest.get('image', '')
    if not isinstance(image, str) or (image and not re.fullmatch(r'[a-z0-9][a-z0-9./_-]*@sha256:[a-f0-9]{64}', image)):
        raise ValueError('发布镜像必须使用固定的 SHA256 摘要。')
    payload = directory / 'source.tar.gz'
    checksum = manifest.get('sha256', '')
    if not re.fullmatch(r'[a-f0-9]{64}', checksum) or not payload.is_file():
        raise ValueError('安装包源码资源或校验值缺失。')
    if hashlib.sha256(payload.read_bytes()).hexdigest() != checksum:
        raise ValueError('安装包资源校验失败，请重新下载。')
    version = manifest.get('version', 'local')
    if not isinstance(version, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._+-]{0,79}', version):
        raise ValueError('安装包版本标识无效。')
    return Bundle(profile, version, image, payload, checksum)
