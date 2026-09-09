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




if __name__ == "__main__":
    unittest.main()
