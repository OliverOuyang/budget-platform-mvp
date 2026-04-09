"""
MMM 模型注册表（多模型管理）
"""

import json
import uuid
import pickle
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from engine.mmm_persistence import MODEL_PATH, load_model, _RestrictedUnpickler


MODELS_DIR = Path(__file__).parent.parent / "data" / "models"
REGISTRY_INDEX = MODELS_DIR / "_index.json"


class ModelRegistry:
    """Multi-model registry with metadata. Stores models as individual pkl files."""

    def __init__(self, models_dir: Path = MODELS_DIR):
        self.models_dir = models_dir
        self.index_path = models_dir / "_index.json"
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self._index = self._load_index()
        self._auto_import_legacy()

    def _load_index(self) -> List[Dict]:
        if self.index_path.exists():
            try:
                with open(self.index_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                return []
        return []

    def _save_index(self):
        with open(self.index_path, "w", encoding="utf-8") as f:
            json.dump(self._index, f, ensure_ascii=False, indent=2)

    def _auto_import_legacy(self):
        """Import old single-file mmm_model.pkl if it exists and isn't already indexed."""
        # Only auto-import when using the default models directory
        if self.models_dir != MODELS_DIR:
            return
        legacy = MODEL_PATH
        if not legacy.exists():
            return
        # Check if already imported
        if any(e.get("legacy_import") for e in self._index):
            return
        model = load_model()
        if model and model.is_fitted:
            model_id = self.save(model, name="legacy_import", auto=True)
            # Mark as legacy import
            for entry in self._index:
                if entry["id"] == model_id:
                    entry["legacy_import"] = True
            self._save_index()

    def save(self, model, name: str = "", auto: bool = False) -> str:
        """Save model to registry. Returns model_id."""
        model_id = str(uuid.uuid4())[:8]
        if not name:
            dv = model.dv_col or "unknown_dv"
            name = f"{dv}_{datetime.now().strftime('%m%d_%H%M')}"

        pkl_path = self.models_dir / f"{model_id}.pkl"
        with open(pkl_path, "wb") as f:
            pickle.dump(model, f)

        entry = {
            "id": model_id,
            "name": name,
            "dv_col": model.dv_col or "",
            "r_squared": round(model.r_squared, 4),
            "train_nrmse": round(model.train_nrmse, 4),
            "test_r_squared": round(model.test_r_squared, 4),
            "decomp_rssd": round(model.decomp_rssd, 4),
            "mape_holdout": round(model.mape_holdout, 4),
            "dw_stat": round(model.dw_stat, 4),
            "cv_mean_r2": round(model.cv_results.get("mean_r2", 0.0), 4),
            "n_channels": len(model.channel_params),
            "created_at": datetime.now().isoformat(),
            "config_summary": {
                "adstock_type": model.training_meta.get("adstock_type", ""),
                "n_trials": model.training_meta.get("n_trials", 0),
                "n_train": model.training_meta.get("n_train", 0),
                "duration_sec": model.training_meta.get("training_duration_sec", 0),
            },
        }
        self._index.append(entry)
        self._save_index()
        return model_id

    def list(self) -> List[Dict]:
        """Return list of all saved models with metadata."""
        return list(self._index)

    def load(self, model_id: str):
        """Load a specific model by ID."""
        from engine.mmm_engine import MMMModel

        pkl_path = self.models_dir / f"{model_id}.pkl"
        if not pkl_path.exists():
            return None
        try:
            with open(pkl_path, "rb") as f:
                result = _RestrictedUnpickler(f).load()
            if not isinstance(result, MMMModel):
                return None
            # Patch fields (same as load_model)
            for attr, default in [
                ('impressions_params', {}), ('_impressions_keys', []),
                ('_use_log_dv', False), ('train_nrmse', result.nrmse if hasattr(result, 'nrmse') else 0.0),
                ('mape_holdout', 0.0), ('dw_stat', 0.0),
                ('cv_results', {}), ('bootstrap_stability', {}),
                ('dv_col', ""), ('training_meta', {}), ('feature_importance', {}),
            ]:
                if not hasattr(result, attr):
                    setattr(result, attr, default)
            return result
        except Exception:
            return None

    def delete(self, model_id: str) -> bool:
        """Delete a model by ID. Returns True if found and deleted."""
        pkl_path = self.models_dir / f"{model_id}.pkl"
        if pkl_path.exists():
            pkl_path.unlink()
        before = len(self._index)
        self._index = [e for e in self._index if e["id"] != model_id]
        if len(self._index) < before:
            self._save_index()
            return True
        return False

    def get_entry(self, model_id: str) -> Optional[Dict]:
        """Get metadata entry for a model."""
        for entry in self._index:
            if entry["id"] == model_id:
                return entry
        return None
