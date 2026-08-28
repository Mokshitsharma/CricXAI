"""Training smoke test: artifacts, metadata schema, SHAP produces values."""

from __future__ import annotations

REQUIRED_META_KEYS = {
    "model_id", "version", "kind", "git_sha", "data_snapshot_hash",
    "data_source", "feature_names", "metrics", "created_at",
}


def test_artifacts_written(trained_env):
    model_dir = trained_env["model_dir"]
    assert (model_dir / "active.json").exists()
    assert (model_dir / "EVAL.md").exists()
    for model_id in ("dismissal_prob", "dismissal_type", "expected_runs"):
        versions = list((model_dir / model_id).iterdir())
        assert versions, f"no version dir for {model_id}"
        art = versions[0]
        assert (art / "model.pkl").exists()
        assert (art / "meta.json").exists()
        assert (art / "eval.md").exists()
        assert (art / "shap_background.parquet").exists()


def test_meta_schema_and_source(trained_env):
    from app.utils.file_io import read_json

    model_dir = trained_env["model_dir"]
    for model_id in ("dismissal_prob", "dismissal_type", "expected_runs"):
        art = next((model_dir / model_id).iterdir())
        meta = read_json(art / "meta.json")
        assert REQUIRED_META_KEYS.issubset(meta), meta.keys()
        assert meta["data_source"] == "mock"
        assert isinstance(meta["feature_names"], list) and meta["feature_names"]


def test_dismissal_prob_metrics_are_sane(active_models):
    metrics = active_models.dismissal_prob.meta["metrics"]
    # Smoke bar only (tiny fixture): the artifact must carry a well-formed,
    # finite metric set and a not-absurd Brier. Discrimination and calibration
    # quality gates run on the full dataset per docs/PHASES.md, not in CI.
    assert set(metrics) >= {"brier", "brier_baseline", "roc_auc", "log_loss", "reliability"}
    assert 0.0 < metrics["brier"] < 0.15
    assert 0.0 < metrics["brier_baseline"] < 0.15
    assert metrics["roc_auc"] >= 0.5
    assert metrics["reliability"], "reliability bins missing"


def test_dismissal_prob_full_dataset_quality_if_present():
    """If the repo's full mock models exist, hold them to the mock sanity bar."""
    from pathlib import Path

    from app.utils.file_io import read_json

    active = Path("data/models/active.json")
    if not active.exists():
        import pytest

        pytest.skip("no full model set in data/models")
    meta = read_json(
        Path("data/models") / read_json(active)["models"]["dismissal_prob"] / "meta.json"
    )
    assert meta["metrics"]["roc_auc"] >= 0.65


def test_shap_produces_values(active_models, trained_env):
    from app.ml.explain import shap_contributions
    from app.ml.features import select_features

    feats = trained_env["features"].head(1)
    x, _ = select_features(feats, active_models.dismissal_prob.feature_names)
    contributions = shap_contributions(active_models.dismissal_prob, x)
    assert len(contributions) == len(active_models.dismissal_prob.feature_names)
    assert any(abs(c[2]) > 0 for c in contributions)
