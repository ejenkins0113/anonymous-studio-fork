"""
Anonymous Studio — OpenFGA seed script (Python).

Creates the store, uploads the model, and writes demo tuples.
Writes OPENFGA_STORE_ID + OPENFGA_MODEL_ID to .env.openfga.

Usage:
    python3 seed.py [--api http://localhost:8080]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import urllib.request
import urllib.error

HERE = Path(__file__).parent


def _post(api: str, path: str, body: dict) -> dict:
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{api}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def _wait_for_api(api: str, retries: int = 30) -> None:
    for i in range(retries):
        try:
            urllib.request.urlopen(f"{api}/healthz", timeout=3)
            return
        except Exception:
            print(f"  ({i+1}/{retries}) OpenFGA not ready, retrying in 2 s…")
            time.sleep(2)
    sys.exit(f"ERROR: OpenFGA not reachable at {api}")


def _build_model_payload() -> dict:
    """
    Build the authorization model payload.
    Prefers the fga CLI (DSL → JSON). Falls back to model.json if present,
    then to the inline definition below.
    """
    # Try fga CLI first
    import shutil, subprocess
    if shutil.which("fga"):
        result = subprocess.run(
            ["fga", "model", "transform", "--file", str(HERE / "model.fga"),
             "--from", "dsl", "--to", "json"],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            return json.loads(result.stdout)

    # Try pre-built JSON
    json_path = HERE / "model.json"
    if json_path.exists():
        return json.loads(json_path.read_text())

    # Inline fallback — mirrors model.fga exactly
    T = "directly_related_user_types"
    USER_AND_GROUP = [{"type": "user"}, {"type": "group", "relation": "member"}]

    def this():
        return {"this": {}}

    def computed(rel):
        return {"computedUserset": {"relation": rel}}

    def union(*children):
        return {"union": {"child": list(children)}}

    return {
        "schema_version": "1.1",
        "type_definitions": [
            {"type": "user"},
            {
                "type": "group",
                "relations": {"member": union(this())},
                "metadata": {"relations": {"member": {T: [{"type": "user"}]}}},
            },
            {
                "type": "card",
                "relations": {
                    "analyst":            union(this()),
                    "reviewer":           union(this()),
                    "compliance_officer": union(this()),
                    "admin":              union(this(), computed("compliance_officer")),
                    "can_view":           union(computed("analyst"), computed("reviewer"),
                                               computed("compliance_officer"), computed("admin")),
                    "can_attest":         union(computed("reviewer"),
                                               computed("compliance_officer"), computed("admin")),
                },
                "metadata": {"relations": {
                    "analyst":            {T: USER_AND_GROUP},
                    "reviewer":           {T: USER_AND_GROUP},
                    "compliance_officer": {T: USER_AND_GROUP},
                    "admin":              {T: USER_AND_GROUP},
                    "can_view":           {T: []},
                    "can_attest":         {T: []},
                }},
            },
            {
                "type": "audit_log",
                "relations": {
                    "compliance_officer": union(this()),
                    "admin":              union(this(), computed("compliance_officer")),
                    "can_export":         union(computed("compliance_officer"), computed("admin")),
                },
                "metadata": {"relations": {
                    "compliance_officer": {T: USER_AND_GROUP},
                    "admin":              {T: USER_AND_GROUP},
                    "can_export":         {T: []},
                }},
            },
            {
                "type": "session",
                "relations": {
                    "analyst":   union(this()),
                    "admin":     union(this()),
                    "can_view":  union(computed("analyst"), computed("admin")),
                },
                "metadata": {"relations": {
                    "analyst":  {T: USER_AND_GROUP},
                    "admin":    {T: USER_AND_GROUP},
                    "can_view": {T: []},
                }},
            },
            {
                "type": "job",
                "relations": {
                    "analyst":    union(this()),
                    "admin":      union(this()),
                    "can_submit": union(computed("analyst"), computed("admin")),
                },
                "metadata": {"relations": {
                    "analyst":    {T: USER_AND_GROUP},
                    "admin":      {T: USER_AND_GROUP},
                    "can_submit": {T: []},
                }},
            },
            {
                "type": "attestation",
                "relations": {
                    "reviewer":           union(this()),
                    "compliance_officer": union(this()),
                    "admin":              union(this(), computed("compliance_officer")),
                    "can_create":         union(computed("reviewer"),
                                               computed("compliance_officer"), computed("admin")),
                },
                "metadata": {"relations": {
                    "reviewer":           {T: USER_AND_GROUP},
                    "compliance_officer": {T: USER_AND_GROUP},
                    "admin":              {T: USER_AND_GROUP},
                    "can_create":         {T: []},
                }},
            },
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default=os.getenv("OPENFGA_API_URL", "http://localhost:8080"))
    args = parser.parse_args()
    api: str = args.api.rstrip("/")

    print(f"==> Waiting for OpenFGA API at {api} …")
    _wait_for_api(api)
    print("    OpenFGA is up.")

    # 1. Create store
    print("==> Creating store 'anonymous-studio' …")
    store = _post(api, "/stores", {"name": "anonymous-studio"})
    store_id = store["id"]
    print(f"    Store ID: {store_id}")

    # 2. Upload model
    print("==> Uploading authorization model …")
    model_payload = _build_model_payload()
    model_resp = _post(api, f"/stores/{store_id}/authorization-models", model_payload)
    model_id = model_resp["authorization_model_id"]
    print(f"    Model ID: {model_id}")

    # 3. Write tuples
    print("==> Writing demo authorization tuples …")
    tuples_data = json.loads((HERE / "seed_tuples.json").read_text())
    _post(api, f"/stores/{store_id}/write", {
        "authorization_model_id": model_id,
        "writes": tuples_data,
    })
    print(f"    {len(tuples_data['tuple_keys'])} tuples written.")

    # 4. Write env file
    env_file = HERE / ".env.openfga"
    env_file.write_text(
        f"# Auto-generated by seed.py\n"
        f"OPENFGA_API_URL={api}\n"
        f"OPENFGA_STORE_ID={store_id}\n"
        f"OPENFGA_MODEL_ID={model_id}\n"
    )
    print(f"==> Wrote {env_file}")

    print()
    print("Done! To enable OpenFGA enforcement in Anonymous Studio:")
    print(f"  export OPENFGA_ENABLED=true")
    print(f"  export OPENFGA_API_URL={api}")
    print(f"  export OPENFGA_STORE_ID={store_id}")
    print(f"  export OPENFGA_MODEL_ID={model_id}")
    print()
    print("  Open the Studio:  http://localhost:3000")


if __name__ == "__main__":
    main()
