from __future__ import annotations

import io
import json
import tarfile

import pytest

from efferents.agents.federation import import_paper_bundle


def _bundle(tmp_path, manifest: dict):
    path = tmp_path / "bundle.tar.gz"
    payload = json.dumps(manifest).encode()
    with tarfile.open(path, "w:gz") as tar:
        info = tarfile.TarInfo("manifest.json")
        info.size = len(payload)
        tar.addfile(info, io.BytesIO(payload))
    return path


def test_import_rejects_traversing_manifest_file(tmp_path):
    bundle = _bundle(
        tmp_path,
        {
            "lab_id": "other-lab",
            "campaign_id": "c1",
            "files": ["../../escaped.txt"],
        },
    )

    with pytest.raises(ValueError, match="unsafe file path"):
        import_paper_bundle(bundle_path=bundle, paper_dir=tmp_path / "paper")


def test_import_rejects_path_like_lab_id(tmp_path):
    bundle = _bundle(
        tmp_path,
        {
            "lab_id": "../../escaped",
            "campaign_id": "c1",
            "files": [],
        },
    )

    with pytest.raises(ValueError, match="unsafe lab_id"):
        import_paper_bundle(bundle_path=bundle, paper_dir=tmp_path / "paper")
