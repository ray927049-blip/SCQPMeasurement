from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scqp_qblox.config import ConfigError, check_parametric_frequency, validate_config


@pytest.fixture
def config():
    path = Path(__file__).parents[1] / "hardware_config.example.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_example_config_is_valid(config):
    validate_config(config)


def test_wrong_qrm_slot_is_rejected(config):
    broken = copy.deepcopy(config)
    broken["modules"]["qrm_rf"]["slot"] = 0
    with pytest.raises(ConfigError, match="slot"):
        validate_config(broken)


def test_1p4_ghz_parametric_drive_is_rejected_for_qcm(config):
    with pytest.raises(ConfigError, match="external source"):
        check_parametric_frequency(config, 1.4e9)


def test_flux_limits_must_stay_inside_safety_limit(config):
    broken = copy.deepcopy(config)
    broken["flux"]["left_max_voltage_v"] = 0.1
    with pytest.raises(ConfigError, match="limits"):
        validate_config(broken)

