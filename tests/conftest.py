"""Shared fixtures.

``trained_env`` builds a small end-to-end artifact set once per test session
(mock data -> features -> the three models) into a temp directory and points
the API's env vars at it, so engine / model / API tests run offline against
real-but-tiny models without touching the repo's ``data/`` tree.
"""

from __future__ import annotations

import pytest

from app.utils.logger import get_logger

_LOGGER = get_logger("tests")


@pytest.fixture(scope="session")
def trained_env(tmp_path_factory) -> dict:
    from scripts import build_features, mock_data, train

    root = tmp_path_factory.mktemp("cricxai_env")
    processed = root / "processed"
    models = root / "models"
    processed.mkdir()
    models.mkdir()

    deliveries, matches = mock_data.generate(num_matches=20, seed=7, logger=_LOGGER)
    deliveries.to_csv(processed / "deliveries.csv", index=False)
    matches.to_csv(processed / "matches.csv", index=False)

    feats = build_features.build_features(deliveries, logger=_LOGGER)
    feats.to_csv(processed / "delivery_features.csv", index=False)

    train.run(processed / "delivery_features.csv", models, _LOGGER)

    return {
        "root": root,
        "processed_dir": processed,
        "model_dir": models,
        "deliveries": deliveries,
        "features": feats,
    }


@pytest.fixture(scope="session")
def active_models(trained_env):
    from app.ml.registry import load_active_models

    return load_active_models(model_dir=trained_env["model_dir"], logger=_LOGGER)


@pytest.fixture
def api_client(trained_env, monkeypatch):
    from fastapi.testclient import TestClient

    from app.api import data as data_module
    from app.api.main import create_app

    monkeypatch.setenv("CRICXAI_MODEL_DIR", str(trained_env["model_dir"]))
    monkeypatch.setenv("CRICXAI_PROCESSED_DIR", str(trained_env["processed_dir"]))
    data_module.get_data_store.cache_clear()

    app = create_app()
    with TestClient(app) as client:
        yield client

    data_module.get_data_store.cache_clear()
