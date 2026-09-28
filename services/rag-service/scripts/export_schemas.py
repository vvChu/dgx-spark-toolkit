#!/usr/bin/env python3
"""
Export OpenAPI JSON Schema and Markdown API Model summaries.
Guarantees Inode Ordering Invariance and deterministic sorting (User Rule #5).
"""

import json
import os
import sys
from pathlib import Path

# Add services/rag-service to sys.path
RAG_SERVICE_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = RAG_SERVICE_DIR.parent.parent
SCHEMAS_DIR = ROOT_DIR / ".md" / "schemas"

sys.path.insert(0, str(RAG_SERVICE_DIR))


def export_schemas() -> None:
    # Set dummy env vars for imports if not present
    os.environ.setdefault("MILVUS_HOST", "localhost")
    os.environ.setdefault("POSTGRES_HOST", "localhost")
    os.environ.setdefault("NEO4J_URI", "bolt://localhost:7687")

    import types
    # Mock heavy ML dependencies to allow fast, headless schema export
    if "retrieval.embeddings.bge_m3_hybrid" not in sys.modules:
        _fake_emb = types.ModuleType("retrieval.embeddings.bge_m3_hybrid")
        class _FakeModel:
            pass
        _fake_emb.BGE_M3_HybridEmbedding = _FakeModel
        sys.modules["retrieval.embeddings.bge_m3_hybrid"] = _fake_emb

    if "FlagEmbedding" not in sys.modules:
        _fake_fe = types.ModuleType("FlagEmbedding")
        sys.modules["FlagEmbedding"] = _fake_fe

    if "sentence_transformers" not in sys.modules:
        _fake_st = types.ModuleType("sentence_transformers")
        _fake_st.CrossEncoder = _FakeModel
        _fake_st.SentenceTransformer = _FakeModel
        sys.modules["sentence_transformers"] = _fake_st

    from main import app

    SCHEMAS_DIR.mkdir(parents=True, exist_ok=True)
    openapi_data = app.openapi()

    openapi_file = SCHEMAS_DIR / "openapi.json"
    with open(openapi_file, "w", encoding="utf-8") as f:
        json.dump(openapi_data, f, indent=2, sort_keys=True, ensure_ascii=False)
    print(f"[OK] Da xuat OpenAPI Schema tai: {openapi_file}")

    # Generate Markdown API Models Summary
    models_file = SCHEMAS_DIR / "API_MODELS.md"
    schemas = openapi_data.get("components", {}).get("schemas", {})

    with open(models_file, "w", encoding="utf-8") as f:
        f.write("# 📋 OpenAPI Schemas & Data Contracts\n\n")
        f.write(f"- **API Title**: `{openapi_data.get('info', {}).get('title')}`\n")
        f.write(f"- **Version**: `{openapi_data.get('info', {}).get('version')}`\n")
        f.write(f"- **Total Schemas**: `{len(schemas)}`\n\n")
        f.write("---\n\n")

        # Deterministic sorting by model name
        for schema_name in sorted(schemas.keys()):
            schema_info = schemas[schema_name]
            f.write(f"### `{schema_name}`\n\n")
            f.write(f"- **Type**: `{schema_info.get('type', 'object')}`\n")
            if "description" in schema_info:
                f.write(f"- **Description**: {schema_info['description']}\n")

            props = schema_info.get("properties", {})
            required_fields = set(schema_info.get("required", []))
            if props:
                f.write("\n| Property | Type | Required | Description |\n")
                f.write("|---|---|:---:|---|\n")
                # Deterministic sorting by property name
                for prop_name in sorted(props.keys()):
                    prop_info = props[prop_name]
                    p_type = prop_info.get("type", prop_info.get("$ref", "any"))
                    if "$ref" in prop_info:
                        p_type = prop_info["$ref"].split("/")[-1]
                    p_req = "✅" if prop_name in required_fields else "❌"
                    p_desc = prop_info.get("description", "-")
                    f.write(f"| `{prop_name}` | `{p_type}` | {p_req} | {p_desc} |\n")
            f.write("\n---\n\n")

    print(f"[OK] Da xuat API Models Markdown tai: {models_file}")


if __name__ == "__main__":
    export_schemas()
