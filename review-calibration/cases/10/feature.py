"""
Feature: migrate settings.json to a versioned schema.

The settings file has no version field, so a future format change has no
migration path. This adds one and rewrites old files in place.
"""
import json
import os
import shutil

SCHEMA_VERSION = 2


def migrate(path):
    """Bring an old settings file up to the current schema. Returns True when
    the file was changed."""
    if not os.path.exists(path):
        return False
    with open(path, encoding="utf-8") as handle:
        blob = json.load(handle)

    if blob.get("schema") == SCHEMA_VERSION:
        return False

    shutil.copy(path, path + ".bak")

    text = json.dumps(blob, indent=2)
    # v1 stored the interval in seconds; v2 stores milliseconds everywhere.
    text = text.replace('"click_s"', '"click_ms"')
    blob = json.loads(text)
    blob["schema"] = SCHEMA_VERSION

    with open(path, "w", encoding="utf-8") as handle:
        json.dump(blob, handle, indent=2)
    return True


def ensure_schema(store):
    changed = migrate(store.path)
    if changed:
        store.__init__(store.path)      # reload what we just rewrote
    return changed
