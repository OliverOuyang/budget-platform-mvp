"""
MMM 模型持久化（保存/加载）
"""

import pickle
import logging
from pathlib import Path
from typing import Optional


MODEL_PATH = Path(__file__).parent.parent / "data" / "mmm_model.pkl"


def save_model(model):
    """Save MMMModel to default path."""
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(MODEL_PATH, "wb") as f:
        pickle.dump(model, f)


ALLOWED_PICKLE_CLASSES = {
    "MMMModel", "ChannelParams", "dict", "list", "tuple", "str", "int", "float", "bool"
}

# Modules safe to unpickle (numpy/pandas types needed for model internals)
ALLOWED_PICKLE_MODULES = {
    "numpy", "pandas", "numpy.core", "numpy._core",
    "builtins", "collections", "codecs", "copy", "copyreg",
    "_codecs", "_collections_abc",
}


class _RestrictedUnpickler(pickle.Unpickler):
    def find_class(self, module: str, name: str):
        if name in ALLOWED_PICKLE_CLASSES:
            return super().find_class(module, name)
        if any(module == m or module.startswith(m + ".") for m in ALLOWED_PICKLE_MODULES):
            return super().find_class(module, name)
        raise pickle.UnpicklingError(f"Disallowed class: {module}.{name}")


def load_model():
    """Load MMMModel from default path with restricted unpickling."""
    from engine.mmm_engine import MMMModel

    if not MODEL_PATH.exists():
        return None
    try:
        with open(MODEL_PATH, "rb") as f:
            result = _RestrictedUnpickler(f).load()
        if not isinstance(result, MMMModel):
            return None
        # Patch missing fields from older model versions
        if not hasattr(result, 'impressions_params'):
            result.impressions_params = {}
        if not hasattr(result, '_impressions_keys'):
            result._impressions_keys = []
        if not hasattr(result, '_use_log_dv'):
            result._use_log_dv = False
        if not hasattr(result, 'train_nrmse'):
            result.train_nrmse = result.nrmse
        if not hasattr(result, 'mape_holdout'):
            result.mape_holdout = 0.0
        if not hasattr(result, 'dw_stat'):
            result.dw_stat = 0.0
        if not hasattr(result, 'cv_results'):
            result.cv_results = {}
        if not hasattr(result, 'bootstrap_stability'):
            result.bootstrap_stability = {}
        if not hasattr(result, 'dv_col'):
            result.dv_col = ""
        if not hasattr(result, 'training_meta'):
            result.training_meta = {}
        if not hasattr(result, 'feature_importance'):
            result.feature_importance = {}
        return result
    except Exception as e:
        logging.warning(f"模型加载失败: {e}")
        return None
