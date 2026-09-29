"""
Feature: export and import a game profile.

Writes one game's settings to a shareable file and reads one back, so a
known-good configuration can be passed to someone else.
"""
import json
import os
import tempfile


def export_dir():
    """Where an exported profile is written."""
    return os.path.join(os.path.expanduser("~"), "Downloads")


def export_profile(store, game_id):
    values = store.game(game_id)
    path = os.path.join(export_dir(), f"{game_id}.afkprofile")
    with open(path, "w") as handle:
        json.dump({"game": game_id, "values": values}, handle, indent=2)
    return path


def import_profile(store, path):
    with open(path) as handle:
        blob = json.load(handle)
    store.put_game(blob["game"], blob["values"])
    return blob["game"]


def profile_name_from_path(path):
    """The game id an export file belongs to, from its filename."""
    return path.split("/")[-1].rsplit(".", 1)[0]


def temp_copy(path):
    """A scratch copy, so an import cannot damage the original."""
    target = os.path.join(tempfile.mkdtemp(), os.path.basename(path))
    with open(path) as src, open(target, "w") as dst:
        dst.write(src.read())
    return target
