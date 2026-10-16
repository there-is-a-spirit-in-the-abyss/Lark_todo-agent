"""Release payload tests use actual tar files, including accidental private inputs."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile

import pytest


BUILD_SCRIPT = Path(__file__).resolve().parents[1] / 'build.py'


def load_builder():
    assert BUILD_SCRIPT.is_file(), 'installer/build.py must implement source packaging'
    spec = importlib.util.spec_from_file_location('installer_build', BUILD_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fixture_project(tmp_path, project='huiyang'):
    inputs = {
        'Dockerfile': 'FROM python:3.11-slim\n',
        '.dockerignore': 'installer\n',
        'pyproject.toml': '[project]\nname="fixture"\nversion="0.1"\n',
        'README.md': 'Fixture',
        'src/app.py': 'print("production")\n',
        'src/secretary.py': '# legitimate production module\n',
        'migrations/versions/one.py': '# migration\n',
        'web/package.json': '{}',
        'web/package-lock.json': '{}',
        'web/index.html': '<html></html>',
        'web/vite.config.mjs': 'export default {}',
        'web/src/main.jsx': 'export default 1',
        'web/public/logo.svg': '<svg/>',
        'installer/project.json': json.dumps({'project': project, 'title': 'fixture', 'default_directory': '/fixture'}),
    }
    private = [
        '.env', '.env.production', 'deploy/team.env', 'src/.env', 'src/app.env',
        'src/private.key', 'src/credentials.json', 'src/local.db-wal',
        'src/state.sqlite3', 'src/screenshots/capture.png', 'src/screenshot.png',
        'src/__pycache__/app.pyc', 'web/src/.env.local',
        'web/node_modules/dependency/index.js', 'web/.runtime/private.json',
        'web/dist/stale.js', 'web/test-results/screen.png', '.runtime/secret.json',
        'tests/private.env', 'installer/bundle/source.tar.gz', 'src/app.log',
        'src/.git/config', 'src/cache/token.json', 'src/id_rsa', 'src/.npmrc',
    ]
    for name, value in {**inputs, **dict.fromkeys(private, 'DO-NOT-SHIP')}.items():
        destination = tmp_path / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(value, encoding='utf-8')
    return inputs, private


@pytest.mark.parametrize('project', ['huiyang', 'team-todo'])
def test_bundle_extracts_clean_production_context_with_verified_manifest(tmp_path, project):
    builder = load_builder()
    inputs, private = fixture_project(tmp_path, project)
    digest_image = 'ghcr.io/example/project@sha256:' + 'a' * 64
    builder.create_bundle(tmp_path, version='v1.2.3', image=digest_image)
    bundle = tmp_path / 'installer/bundle'
    archive = bundle / 'source.tar.gz'
    manifest = json.loads((bundle / 'manifest.json').read_text(encoding='utf-8'))
    assert manifest == {'project': project, 'version': 'v1.2.3', 'image': digest_image,
                        'sha256': hashlib.sha256(archive.read_bytes()).hexdigest()}
    with tarfile.open(archive) as payload:
        names = set(payload.getnames())
        assert set(inputs) - {'installer/project.json'} <= names
        assert not names.intersection(private)
        assert all(not entry.issym() and not entry.islnk() and entry.isfile() for entry in payload)
        payload.extractall(tmp_path / 'extracted', filter='data')
    assert (tmp_path / 'extracted/web/src/main.jsx').read_text() == 'export default 1'
    assert not any(b'DO-NOT-SHIP' in p.read_bytes() for p in (tmp_path / 'extracted').rglob('*') if p.is_file())


@pytest.mark.parametrize('image', ['ghcr.io/example/project:latest', 'example@sha256:no', 'https://ghcr.io/p'])
def test_mutable_or_malformed_image_is_rejected(tmp_path, image):
    builder = load_builder()
    fixture_project(tmp_path)
    with pytest.raises(ValueError, match='digest'):
        builder.create_bundle(tmp_path, image=image)
    assert not (tmp_path / 'installer/bundle/manifest.json').exists()


def test_local_bundle_has_no_registry_and_is_reproducible(tmp_path):
    builder = load_builder()
    fixture_project(tmp_path)
    first = builder.create_bundle(tmp_path)
    second = builder.create_bundle(tmp_path)
    assert first == second
    assert first['image'] == ''
    assert first['version'] == 'local'


def test_missing_frontend_lock_fails_before_shipping_incomplete_source(tmp_path):
    builder = load_builder()
    fixture_project(tmp_path)
    (tmp_path / 'web/package-lock.json').unlink()
    with pytest.raises(ValueError, match='package-lock'):
        builder.create_bundle(tmp_path)


@pytest.mark.parametrize('version', ['', 'has spaces', 'v1/next', '-v1', 'x' * 81, 'v1\n'])
def test_version_rejects_values_that_cannot_be_loaded_by_installer(tmp_path, version):
    builder = load_builder()
    fixture_project(tmp_path)
    with pytest.raises(ValueError, match='version'):
        builder.create_bundle(tmp_path, version=version)
    assert not (tmp_path / 'installer/bundle/manifest.json').exists()


@pytest.mark.parametrize('version', ['v1.2.3-rc1+build_2', 'x' * 80])
def test_version_accepts_release_names_up_to_loader_boundary(tmp_path, version):
    builder = load_builder()
    fixture_project(tmp_path)
    assert builder.create_bundle(tmp_path, version=version)['version'] == version


def test_real_cli_bundle_only_can_run_without_pyinstaller(tmp_path):
    fixture_project(tmp_path)
    isolated_script = tmp_path / 'installer/build.py'
    shutil.copyfile(BUILD_SCRIPT, isolated_script)
    result = subprocess.run([sys.executable, str(isolated_script), '--bundle-only'],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert 'source.tar.gz' in result.stdout
    assert (tmp_path / 'installer/bundle/manifest.json').is_file()
