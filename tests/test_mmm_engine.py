import pytest
import pickle
import sys
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

from engine.mmm_engine import load_model


def test_load_model_returns_none_when_file_missing(tmp_path):
    with patch("engine.mmm_engine.MODEL_PATH", tmp_path / "nonexistent.pkl"):
        result = load_model()
        assert result is None


def test_load_model_rejects_malicious_pickle(tmp_path):
    """pickle.load security: ensure only MMMModel instances are accepted."""
    malicious = b"\x80\x04\x95\x11\x00\x00\x00\x00\x00\x00\x00"
    pkl_path = tmp_path / "malicious.pkl"
    pkl_path.write_bytes(malicious)
    with patch("engine.mmm_engine.MODEL_PATH", pkl_path):
        result = load_model()
        # Should return None (rejected), not execute arbitrary code
        assert result is None
