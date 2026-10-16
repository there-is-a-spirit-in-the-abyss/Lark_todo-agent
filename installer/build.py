"""Build a credential-free source fallback and Windows x64 standalone installer."""
from __future__ import annotations

import argparse
import fnmatch
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import tarfile


ROOT = Path(__file__).resolve().parents[1]
ROOT_FILES = {'Dockerfile', '.dockerignore', 'pyproject.toml', 'README.md', 'alembic.ini', 'LICENSE', 'LICENSE.md'}
SOURCE_DIRS = {'src', 'team_todo', 'migrations'}
EXCLUDED_DIRS = {
    '.git', '.venv', 'venv', '.runtime', '__pycache__', 'node_modules',
    '.pytest_cache', '.pytest_tmp', '.mypy_cache', '.ruff_cache', '.cache', 'cache',
    'dist', 'build', 'installer', 'tests', 'test-results', 'playwright-report',
    'screenshots', 'screenshot', 'logs', 'data', 'postgres_data', 'backups',
}
EXCLUDED_FILES = (
    '.env*', '*.env', '*.env.*', '*.db*', '*.sqlite*', '*.log', '*.pyc', '*.pyo',
    '*.pem', '*.key', '*.p12', '*.pfx', 'id_rsa*', 'id_ed25519*',
    '*credentials*.json', '*credentials*.yaml', '*credentials*.yml',
    '*secret*.json', '*secret*.yaml', '*secret*.yml', '*secret*.txt',
    '*screenshot*', '.npmrc', '.pypirc', '.netrc',
)
IMAGE_PATTERN = re.compile(r'ghcr\.io/[a-z0-9][a-z0-9._/-]*@sha256:[0-9a-f]{64}\Z')


def production_files(root: Path):
    """Allow production inputs only and never traverse runtime trees or symlinks."""
    candidates = [root / name for name in ROOT_FILES]
    for directory in sorted(SOURCE_DIRS | {'web'}):
        base = root / directory
        if not base.is_dir() or base.is_symlink():
            continue
        for current, directories, files in os.walk(base, followlinks=False):
            directories[:] = sorted(name for name in directories
                                    if name.lower() not in EXCLUDED_DIRS
                                    and not (Path(current) / name).is_symlink())
            candidates.extend(Path(current) / name for name in files)
    for path in sorted(candidates):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(root)
        parts = relative.parts
        if any(part.lower() in EXCLUDED_DIRS for part in parts[:-1]):
            continue
        if any(fnmatch.fnmatch(path.name.lower(), pattern) for pattern in EXCLUDED_FILES):
            continue
        if parts[0] == 'web' and not (
            len(parts) >= 3 and parts[1] in {'src', 'public'}
            or len(parts) == 2 and (
                parts[1] in {'index.html', 'package.json', 'package-lock.json'}
                or parts[1].startswith(('vite.config.', 'tsconfig.', 'postcss.config.', 'tailwind.config.'))
            )
        ):
            continue
        yield path


def create_bundle(root: Path = ROOT, *, version: str = 'local', image: str = '') -> dict:
    root = Path(root).resolve()
    if image and not IMAGE_PATTERN.fullmatch(image):
        raise ValueError('image must be a lowercase ghcr.io repository with an immutable sha256 digest')
    if not isinstance(version, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._+-]{0,79}', version):
        raise ValueError('version must start with a letter or digit, use only A-Z a-z 0-9 . _ + -, and contain at most 80 characters')
    profile = json.loads((root / 'installer/project.json').read_text(encoding='utf-8'))
    if profile.get('project') not in {'huiyang', 'team-todo'}:
        raise ValueError('project.json must identify huiyang or team-todo')
    files = list(production_files(root))
    included = {path.relative_to(root).as_posix() for path in files}
    required = {'Dockerfile', '.dockerignore', 'pyproject.toml', 'README.md',
                'web/package.json', 'web/package-lock.json', 'web/index.html'}
    if missing := required - included:
        raise ValueError('missing production inputs: ' + ', '.join(sorted(missing)))
    content = io.BytesIO()
    with gzip.GzipFile(fileobj=content, mode='wb', filename='', mtime=0) as compressed:
        with tarfile.open(fileobj=compressed, mode='w') as archive:
            for path in files:
                data = path.read_bytes()
                info = tarfile.TarInfo(path.relative_to(root).as_posix())
                info.size, info.mode, info.mtime = len(data), 0o644, 0
                archive.addfile(info, io.BytesIO(data))
    payload = content.getvalue()
    manifest = {'project': profile['project'], 'version': version, 'image': image,
                'sha256': hashlib.sha256(payload).hexdigest()}
    bundle = root / 'installer/bundle'
    bundle.mkdir(parents=True, exist_ok=True)
    (bundle / 'source.tar.gz').write_bytes(payload)
    (bundle / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    return manifest


def build_executable(root: Path, manifest: dict) -> Path:
    if sys.platform != 'win32' or platform.machine().lower() not in {'amd64', 'x86_64'}:
        raise RuntimeError('The executable must be built with Windows x64 Python 3.11.')
    if sys.version_info[:2] != (3, 11):
        raise RuntimeError('Use Python 3.11 to build the installer.')
    directory = root / 'installer'
    name = manifest['project'] + '-setup'
    subprocess.run([
        sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onefile', '--windowed',
        '--name', name, '--distpath', str(directory / 'dist'),
        '--workpath', str(directory / 'build'), '--specpath', str(directory / 'build'),
        '--paths', str(directory), '--add-data', f'{directory / "bundle"};bundle',
        '--add-data', f'{directory / "project.json"};.',
        '--collect-all', 'paramiko', str(directory / 'launch.py'),
    ], cwd=root, check=True)
    executable = directory / 'dist' / (name + '.exe')
    checksum = hashlib.sha256(executable.read_bytes()).hexdigest()
    executable.with_suffix('.exe.sha256').write_text(f'{checksum}  {executable.name}\n', encoding='ascii')
    return executable


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', default='', help='Immutable ghcr.io/owner/repository@sha256:...')
    parser.add_argument('--version', default='local')
    parser.add_argument('--bundle-only', action='store_true', help='Only create the clean source bundle')
    args = parser.parse_args()
    try:
        manifest = create_bundle(version=args.version, image=args.image)
        print(f'Created installer/bundle/source.tar.gz ({manifest["sha256"]})')
        if not args.bundle_only:
            print(build_executable(ROOT, manifest))
    except (ValueError, RuntimeError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(1, f'Build failed: {error}\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
