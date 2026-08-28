"""SHAP attributions for a single dismissal-probability prediction.

Uses ``shap.TreeExplainer`` on the raw LightGBM tree (``base_model`` on the
``dismissal_prob`` artifact) — the calibrated wrapper is not a tree and can't
be explained directly, but the calibration is monotonic so the sign and
ranking of contributions carry over.
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

from app.ml.registry import LoadedModel
from app.utils.logger import get_logger

_EXPLAINER_CACHE: dict[int, object] = {}


def _get_explainer(model: LoadedModel):
    tree = model.base_model if model.base_model is not None else model.estimator
    key = id(tree)
    if key not in _EXPLAINER_CACHE:
        import shap

        _EXPLAINER_CACHE[key] = shap.TreeExplainer(tree)
    return _EXPLAINER_CACHE[key]


def shap_contributions(
    model: LoadedModel, x_row: pd.DataFrame, logger=None
) -> list[tuple[str, float, float]]:
    """Return ``[(feature_name, feature_value, shap_value), ...]`` sorted by |shap| desc.

    ``x_row`` is a single-row DataFrame already aligned to
    ``model.feature_names``.
    """
    logger = logger or get_logger(__name__)
    try:
        explainer = _get_explainer(model)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            values = explainer.shap_values(x_row)
        if isinstance(values, list):  # binary classifier: [class0, class1]
            values = values[1]
        elif values.ndim == 3:  # (n, features, classes)
            values = values[:, :, 1]
        values = np.asarray(values).reshape(len(model.feature_names))
    except Exception as exc:  # noqa: BLE001 - explanations are best-effort
        logger.warning("SHAP failed, returning no contributions: %s", exc)
        return []

    row = x_row.iloc[0]
    contributions = [
        (name, float(row[name]), float(values[i]))
        for i, name in enumerate(model.feature_names)
    ]
    contributions.sort(key=lambda t: abs(t[2]), reverse=True)
    return contributions
