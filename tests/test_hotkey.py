"""The hotkey engine: identity, matching, labels and persistence."""
import json
import unittest

from .context import app, kb, needs_display, hotkey, record


@needs_display
class KeyIdentity(unittest.TestCase):
    def test_modifier_sides_collapse(self):
        self.assertEqual(app._mod_base(kb.Key.ctrl_l), "ctrl")
        self.assertEqual(app._mod_base(kb.Key.ctrl_r), "ctrl")
        self.assertEqual(app._mod_base(kb.Key.shift_l), "shift")

    def test_altgr_is_not_alt(self):
        # On a German layout AltGr produces characters; treating it as Alt
        # would make AltGr+key indistinguishable from Alt+key.
        #
        # Mac keyboards have no AltGr, and pynput's darwin backend aliases
        # Key.alt_gr onto Key.alt -- the member's own name is "alt" there, so
        # there is nothing to keep apart. Assert the distinction only where the
        # platform actually makes one.
        if kb.Key.alt_gr.name == "alt_gr":
            self.assertEqual(app._mod_base(kb.Key.alt_gr), "altgr")
        else:
            self.assertEqual(app._mod_base(kb.Key.alt_gr), "alt")
        self.assertEqual(app._mod_base(kb.Key.alt_l), "alt")

    def test_plain_keys_are_not_modifiers(self):
        self.assertIsNone(app._mod_base(kb.Key.f6))
        self.assertIsNone(app._mod_base(kb.KeyCode.from_char("h")))

    def test_record_keeps_every_identifier(self):
        name, vk, char = record(kb.Key.f6)
        self.assertEqual(name, "f6")
        name, vk, char = record(kb.KeyCode.from_char("H"))
        self.assertIsNone(name)
        self.assertEqual(char, "h")

    def test_same_key_matches_on_any_field(self):
        self.assertTrue(app._same_key(("f6", 1, None), ("f6", 999, None)))
        self.assertTrue(app._same_key((None, 42, None), (None, 42, "x")))
        self.assertTrue(app._same_key((None, None, "h"), (None, None, "h")))
        self.assertFalse(app._same_key(("f6", None, None), ("f7", None, None)))


@needs_display
class Labels(unittest.TestCase):
    def test_named_and_char_keys(self):
        self.assertEqual(hotkey(set(), [kb.Key.page_up]).label(), "Page Up")
        self.assertEqual(hotkey(set(), [kb.KeyCode.from_char("h")]).label(), "H")

    def test_uppercase_only_when_it_round_trips(self):
        # "ß".upper() is "SS" and Turkish dotless "ı".upper() is "I" -- a
        # different key. Showing either would misname the binding.
        self.assertEqual(hotkey(set(), [kb.KeyCode.from_char("ß")]).label(), "ß")
        self.assertEqual(hotkey(set(), [kb.KeyCode.from_char("ı")]).label(), "ı")
        self.assertEqual(hotkey(set(), [kb.KeyCode.from_char("ä")]).label(), "Ä")

    def test_modifier_order_is_stable(self):
        self.assertEqual(hotkey({"shift", "ctrl"}, [kb.Key.f6]).label(),
                         "Ctrl + Shift + F6")

    def test_chord_of_three(self):
        self.assertEqual(hotkey(set(), [kb.Key.f6, kb.Key.f7, kb.Key.f8]).label(),
                         "F6 + F7 + F8")


@needs_display
class Matching(unittest.TestCase):
    def test_exact_chord_matches(self):
        hk = hotkey({"ctrl"}, [kb.Key.f6, kb.Key.f7])
        held = [record(kb.Key.f6), record(kb.Key.f7)]
        self.assertTrue(hk.matches({"ctrl"}, held))

    def test_order_does_not_matter(self):
        hk = hotkey(set(), [kb.Key.f6, kb.Key.f7])
        self.assertTrue(hk.matches(set(), [record(kb.Key.f7), record(kb.Key.f6)]))

    def test_subset_does_not_match(self):
        hk = hotkey(set(), [kb.Key.f6, kb.Key.f7])
        self.assertFalse(hk.matches(set(), [record(kb.Key.f6)]))

    def test_wrong_modifiers_do_not_match(self):
        hk = hotkey({"ctrl"}, [kb.Key.f6])
        held = [record(kb.Key.f6)]
        self.assertFalse(hk.matches(set(), held))
        self.assertFalse(hk.matches({"shift"}, held))
        self.assertFalse(hk.matches({"ctrl", "shift"}, held))



@needs_display
class Watcher(unittest.TestCase):
    """
    HotkeyWatcher without synthesising key presses.

    The slow sweep covers it end to end, but that one is excluded from the
    pull-request suite, which left the arming and debounce logic untested on
    every PR. Driving _press/_release directly is deterministic and instant.
    """

    def setUp(self):
        self.hits = []
        self.watcher = app.HotkeyWatcher(hotkey({"ctrl"}, [kb.Key.f6]),
                                         lambda: self.hits.append(1))
        # Deliberately not started: no listener, no display interaction, just
        # the state machine.

    def press(self, *keys):
        for key in keys:
            self.watcher._press(key)

    def release(self, *keys):
        for key in keys:
            self.watcher._release(key)

    def test_fires_on_the_complete_chord(self):
        self.press(kb.Key.ctrl, kb.Key.f6)
        self.assertEqual(len(self.hits), 1)

    def test_does_not_fire_without_the_modifier(self):
        self.press(kb.Key.f6)
        self.assertEqual(self.hits, [])

    def test_does_not_fire_with_an_extra_modifier(self):
        self.press(kb.Key.ctrl, kb.Key.shift, kb.Key.f6)
        self.assertEqual(self.hits, [])

    def test_holding_does_not_repeat(self):
        self.press(kb.Key.ctrl, kb.Key.f6)
        self.press(kb.Key.f6, kb.Key.f6)      # auto-repeat
        self.assertEqual(len(self.hits), 1)

    def test_rearms_after_release(self):
        self.watcher.DEBOUNCE_S = 0           # timing is not what is under test
        self.press(kb.Key.ctrl, kb.Key.f6)
        self.release(kb.Key.f6)
        self.press(kb.Key.f6)
        self.assertEqual(len(self.hits), 2)

    def test_debounce_suppresses_an_immediate_second_fire(self):
        self.press(kb.Key.ctrl, kb.Key.f6)
        self.release(kb.Key.f6)
        self.press(kb.Key.f6)                 # inside the 250 ms window
        self.assertEqual(len(self.hits), 1)

    def test_left_and_right_modifiers_are_interchangeable(self):
        self.press(kb.Key.ctrl_r, kb.Key.f6)
        self.assertEqual(len(self.hits), 1)


@needs_display
class Recorder(unittest.TestCase):
    def drive(self, keys):
        rec = app.HotkeyRecorder()
        for key in keys:
            rec.press(key)
        for key in reversed(keys):
            rec.release(key)
        return rec.result()

    def test_single_key(self):
        self.assertEqual(self.drive([kb.Key.f6]).label(), "F6")

    def test_modifier_plus_key(self):
        self.assertEqual(self.drive([kb.Key.ctrl, kb.Key.f6]).label(), "Ctrl + F6")

    def test_three_key_chord(self):
        self.assertEqual(self.drive([kb.Key.f6, kb.Key.f7, kb.Key.f8]).label(),
                         "F6 + F7 + F8")

    def test_caps_at_three_keys(self):
        result = self.drive([kb.Key.f5, kb.Key.f6, kb.Key.f7, kb.Key.f8])
        self.assertEqual(len(result.keys), app.MAX_CHORD)

    def test_escape_cancels(self):
        rec = app.HotkeyRecorder()
        rec.press(kb.Key.esc)
        self.assertIsNone(rec.result())

    def test_modifier_alone_is_not_a_hotkey(self):
        rec = app.HotkeyRecorder()
        rec.press(kb.Key.ctrl)
        rec.release(kb.Key.ctrl)
        self.assertIsNone(rec.result())



@needs_display
class Persistence(unittest.TestCase):
    def test_round_trip(self):
        for mods, keys in [(set(), [kb.Key.f6]),
                           ({"ctrl", "shift"}, [kb.Key.f6, kb.Key.f7]),
                           (set(), [kb.KeyCode.from_char("ä")]),
                           ({"alt"}, [kb.KeyCode.from_char("+"), kb.Key.f9])]:
            with self.subTest(keys=keys):
                original = hotkey(mods, keys)
                blob = json.loads(json.dumps(original.to_json()))
                restored = app.Hotkey.from_json(blob)
                self.assertEqual(restored.label(), original.label())
                self.assertTrue(restored.matches(set(mods),
                                                 [record(k) for k in keys]))

    def test_a_dropped_vk_is_not_silently_survivable(self):
        # KeyCode.from_char() leaves vk as None, so a round-trip built from one
        # passes even if to_json stops writing vk at all. Use a record that
        # carries one -- the shape a real X11 or Win32 event has.
        original = app.Hotkey(set(), [(None, 97, "a")])
        restored = app.Hotkey.from_json(json.loads(json.dumps(original.to_json())))
        self.assertEqual(restored.keys[0][1], 97, "the virtual key code was lost")
        # And it must still match an event carrying only the vk, which is what
        # arrives once a modifier changes the character.
        self.assertTrue(restored.matches(set(), [(None, 97, None)]))

    def test_bad_modifiers_are_rejected_not_filtered(self):
        # Filtering turned a saved Ctrl+Shift+F6 into an armed, firing Ctrl+F6:
        # a global hotkey the user never recorded, with a plausible label.
        good = {"mods": ["ctrl", "shift"], "keys": [["f6", 65475, None]]}
        self.assertEqual(app.Hotkey.from_json(good).label(), "Ctrl + Shift + F6")
        for mods in (["ctrl", 0], ["ctrl", None], ["ctrl", "bogus"], ["CTRL"], [""]):
            with self.subTest(mods=mods):
                self.assertIsNone(app.Hotkey.from_json(
                    {"mods": mods, "keys": [["f6", 65475, None]]}))

    def test_unknown_key_names_are_rejected(self):
        # Shape is not vocabulary: "no_such_key" is a string of the right type
        # and would arm a hotkey nothing can ever satisfy.
        for name in ("bogus", "", "no_such_key", "F6"):
            with self.subTest(name=name):
                self.assertIsNone(app.Hotkey.from_json({"keys": [[name, None, None]]}))
        self.assertIsNotNone(app.Hotkey.from_json({"keys": [["f6", None, None]]}))

    def test_unhashable_modifiers_do_not_raise(self):
        # `m not in _MOD_ORDER` hashes m. A list or a dict in "mods" raised
        # TypeError out of __init__ and the window never opened -- a damaged
        # setting must start clean, never block startup.
        for mods in ([["ctrl"]], [{"ctrl": 1}], [{"a"}], [("ctrl",)]):
            with self.subTest(mods=mods):
                self.assertIsNone(app.Hotkey.from_json(
                    {"mods": mods, "keys": [["f6", 65475, None]]}))

    def test_every_rejection_path_is_reachable(self):
        # One case per guard, chosen so that removing that guard fails here
        # rather than surviving because a later one happens to catch the same
        # input. Two of these were originally chosen badly and did exactly
        # that: {"mods": "ctrl"} and {"keys": ["f6"]} are both rejected by a
        # later check, so the guards they were named after could be deleted
        # with the suite still green. The dict and int cases reach them.
        cases = {
            "not a dict": "nope",
            "keys missing": {"mods": []},
            "keys not a sequence": {"keys": 7},
            "keys empty": {"keys": []},
            "mods not a sequence": {"keys": [["f6", 1, None]], "mods": "ctrl"},
            # A dict *is* iterable and yields its keys, so without the
            # isinstance check this is silently accepted as Ctrl + F6 -- the
            # original filtering bug, wearing a plausible label.
            "mods is a dict": {"keys": [["f6", 1, None]], "mods": {"ctrl": 1}},
            "mods wrong type": {"keys": [["f6", 1, None]], "mods": [1]},
            "mods unknown": {"keys": [["f6", 1, None]], "mods": ["hyper"]},
            "entry not a sequence": {"keys": ["f6"]},
            # An int is not iterable at all, so without the isinstance check
            # this raises TypeError out of __init__ and the window never
            # opens -- the same failure as the unhashable modifier.
            "entry is an int": {"keys": [5]},
            "entry too long": {"keys": [["f6", 1, None, "x"]]},
            "entry empty": {"keys": [[]]},
            "name wrong type": {"keys": [[7, None, None]]},
            "vk wrong type": {"keys": [[None, "97", None]]},
            "char wrong type": {"keys": [[None, None, 5]]},
            "entry all null": {"keys": [[None, None, None]]},
            "unknown key name": {"keys": [["no_such_key", None, None]]},
        }
        for label, blob in cases.items():
            with self.subTest(case=label):
                self.assertIsNone(app.Hotkey.from_json(blob), label)

    def test_malformed_input_yields_none(self):
        # "keys": "nope" raises nothing on its own -- iterating a string hands
        # back characters and would build a plausible hotkey out of garbage.
        for blob in ({}, {"keys": []}, {"keys": "nope"}, {"mods": ["ctrl"]},
                     {"keys": [[]]}, {"keys": [[None, None, None]]},
                     {"keys": [["f6"]], "mods": "ctrl"},
                     {"keys": [[1, 2, 3]]}, "not a dict", None):
            with self.subTest(blob=blob):
                self.assertIsNone(app.Hotkey.from_json(blob if blob else {}))


@needs_display
class InputPermission(unittest.TestCase):
    """
    macos_input_permitted() decides whether a listener may be started at all.

    It needs tests of its own: keying a skip off it meant forcing it False just
    skipped the tests that would have caught the change, and forcing it True
    changed nothing observable anywhere.
    """

    def test_true_off_darwin(self):
        if app.sys.platform == "darwin":
            self.skipTest("this asserts the non-macOS short circuit")
        self.assertIs(app.macos_input_permitted(), True)

    def test_false_on_darwin_when_the_question_cannot_be_answered(self):
        # Pretend to be macOS on a machine with no ApplicationServices. The two
        # mistakes do not cost the same: a wrong True is an uncatchable SIGTRAP
        # that takes the window with it, a wrong False is a message.
        if app.sys.platform == "darwin":
            self.skipTest("only meaningful where the framework is absent")
        original = app.sys.platform
        app.sys.platform = "darwin"
        try:
            self.assertIs(app.macos_input_permitted(), False)
        finally:
            app.sys.platform = original

if __name__ == "__main__":
    unittest.main()
