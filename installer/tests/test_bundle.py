import hashlib
import json

import pytest

from deployer.bundle import load_bundle


def make_bundle(tmp_path, payload=b'not-a-secret-source', **overrides):
    (tmp_path / 'source.tar.gz').write_bytes(payload)
    manifest = {'project':'team-todo', 'version':'local', 'image':'', 'sha256':hashlib.sha256(payload).hexdigest()}
    manifest.update(overrides)
    (tmp_path / 'manifest.json').write_text(json.dumps(manifest))


def test_bundle_integrity_is_checked_before_any_server_connection(tmp_path):
    make_bundle(tmp_path)
    assert load_bundle(tmp_path).profile.id == 'team-todo'
    (tmp_path / 'source.tar.gz').write_bytes(b'tampered')
    with pytest.raises(ValueError, match='校验'):
        load_bundle(tmp_path)


def test_released_image_must_be_immutable_not_a_mutable_latest_tag(tmp_path):
    make_bundle(tmp_path, image='ghcr.io/owner/project:latest')
    with pytest.raises(ValueError):
        load_bundle(tmp_path)


def test_published_digest_image_is_accepted(tmp_path):
    make_bundle(tmp_path, image='ghcr.io/owner/project@sha256:' + 'a'*64)
    assert load_bundle(tmp_path).image.endswith('a'*64)
