from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OPENFGA_DIR = ROOT / "deploy" / "openfga"


def _load_seed_module():
    spec = importlib.util.spec_from_file_location("openfga_seed", OPENFGA_DIR / "seed.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_model_has_unique_type_names():
    seed_module = _load_seed_module()
    model = seed_module._build_model_payload()
    type_names = [type_def["type"] for type_def in model["type_definitions"]]
    assert len(type_names) == len(set(type_names))


def test_seed_tuples_relations_exist_in_model():
    seed_module = _load_seed_module()
    model = seed_module._build_model_payload()
    relations_by_type = {
        type_def["type"]: set(type_def.get("relations", {}).keys())
        for type_def in model["type_definitions"]
    }
    tuple_keys = json.loads((OPENFGA_DIR / "seed_tuples.json").read_text())["tuple_keys"]

    for item in tuple_keys:
        obj_type = item["object"].split(":", 1)[0]
        assert item["relation"] in relations_by_type[obj_type]
