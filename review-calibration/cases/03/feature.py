"""
Feature: remember the window position between sessions.

Stores the geometry string in settings.json and restores it on the next start,
so the window comes back where it was left.
"""
import json


def load_geometry(store):
    """Return a Tk geometry string, or None when nothing usable is stored."""
    try:
        blob = store.data.get("window") or {}
        return "%dx%d+%d+%d" % (blob["w"], blob["h"], blob["x"], blob["y"])
    except Exception:
        return None


def save_geometry(store, root):
    store.data["window"] = {
        "w": root.winfo_width(), "h": root.winfo_height(),
        "x": root.winfo_x(), "y": root.winfo_y(),
    }
    store.save()


def apply_geometry(root, store):
    geometry = load_geometry(store)
    if geometry:
        root.geometry(geometry)
