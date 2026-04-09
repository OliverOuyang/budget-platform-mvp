"""MMM Engine package — re-exports for backward compatibility."""

from engine.mmm_engine import (  # noqa: F401
    geometric_adstock, weibull_adstock, hill_saturation,
    ChannelParams, MMMModel, MMMTrainer,
)
from engine.mmm_persistence import save_model, load_model, MODEL_PATH  # noqa: F401
from engine.mmm_registry import ModelRegistry, MODELS_DIR  # noqa: F401
