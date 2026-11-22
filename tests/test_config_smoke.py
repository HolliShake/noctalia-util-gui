import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest.mock import patch

import config


class ConfigSmokeTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.config_path = Path(self.temp_dir.name, "config.toml")
        self.config_path.write_text(
            '[settings]\nreset = "stale"\n', encoding="utf-8")
        source = config.ConfigSource(
            "umbriel",
            {
                "name": "Umbriel",
                "load_paths": [str(self.config_path)],
                "save_path": str(self.config_path),
            },
        )
        source.load()
        self.manager = config.ConfigManager.__new__(config.ConfigManager)
        self.manager.sources = {"umbriel": source}
        self.manager.dynamic_schema_edits = {}
        self.manager.schema_choice_rules = []

    def test_all_form_value_kinds_round_trip_through_config(self):
        variables = {
            "umbriel:settings.enabled": True,
            "umbriel:settings.count": "8",
            "umbriel:settings.opacity": "0.25",
            "umbriel:settings.label": "workspace",
            "umbriel:settings.mode": "overlay",
            "umbriel:settings.color": "#AABBCC",
            "umbriel:settings.words": "one, two",
            "umbriel:settings.integers": "2, 4",
            "umbriel:settings.fractions": "0.1, 0.5",
            "umbriel:settings.reset": "",
        }
        metadata = {
            "umbriel:settings.enabled": {"kind": "boolean"},
            "umbriel:settings.count": {
                "kind": "number", "number_type": "int"},
            "umbriel:settings.opacity": {
                "kind": "number", "number_type": "float"},
            "umbriel:settings.label": {"kind": "text"},
            "umbriel:settings.mode": {"kind": "choice"},
            "umbriel:settings.color": {"kind": "color"},
            "umbriel:settings.words": {"kind": "list", "item_type": "str"},
            "umbriel:settings.integers": {"kind": "list", "item_type": "int"},
            "umbriel:settings.fractions": {
                "kind": "list", "item_type": "float"},
            "umbriel:settings.reset": {
                "kind": "choice", "default_only": True, "default_value": ""},
        }
        form_state = {
            "variables": variables,
            "raw_blocks": {
                "umbriel:window_rule": (
                    '[[window_rule]]\nmatch = "app"\n'),
            },
            "metadata": metadata | {
                "umbriel:window_rule": {"kind": "aot"},
            },
            "dynamic_schema_edits": {"experimental.enabled": True},
            "keybind_rows": [
                ("SUPER+X", "launch", 'repeat=true, rate=1.5, count=3, mode="smart"'),
            ],
            "keybinds_touched": True,
        }

        with patch(
                "config.run_official_validator",
                return_value={
                    "installed": True,
                    "ok": True,
                    "diagnostics": [],
                    "raw": "",
                }) as validator:
            result = self.manager.prepare_source("umbriel", form_state)

        self.assertTrue(result["ok"], result)
        self.assertFalse(result["fatal"])
        validator.assert_called_once()
        self.manager.commit(
            "umbriel", result["text"],
            lambda _source: self.fail("unexpected overwrite confirmation"))
        parsed = tomllib.loads(result["text"])
        self.assertEqual(
            tomllib.loads(self.config_path.read_text(encoding="utf-8")),
            parsed)

        self.assertIs(type(parsed["settings"]["enabled"]), bool)
        self.assertIs(type(parsed["settings"]["count"]), int)
        self.assertIs(type(parsed["settings"]["opacity"]), float)
        self.assertIs(type(parsed["settings"]["label"]), str)
        self.assertIs(type(parsed["settings"]["mode"]), str)
        self.assertIs(type(parsed["settings"]["color"]), str)
        self.assertEqual(parsed["settings"]["words"], ["one", "two"])
        self.assertEqual(parsed["settings"]["integers"], [2, 4])
        self.assertTrue(all(
            type(value) is float for value in parsed["settings"]["fractions"]))
        self.assertNotIn("reset", parsed.get("settings", {}))
        self.assertEqual(parsed["window_rule"], [{"match": "app"}])
        self.assertIs(
            type(parsed["experimental"]["enabled"]), bool)
        keybind = parsed["keybinds"]["SUPER+X"]
        self.assertEqual(keybind["action"], "launch")
        self.assertIs(type(keybind["repeat"]), bool)
        self.assertIs(type(keybind["rate"]), float)
        self.assertIs(type(keybind["count"]), int)
        self.assertIs(type(keybind["mode"]), str)

    def test_invalid_integer_and_float_inputs_are_rejected(self):
        base_state = {
            "variables": {},
            "raw_blocks": {},
            "metadata": {},
            "dynamic_schema_edits": {},
            "keybind_rows": [],
            "keybinds_touched": False,
        }
        invalid_cases = (
            ("umbriel:settings.count", "1.5", "int"),
            ("umbriel:settings.opacity", "not-a-number", "float"),
        )
        for key, raw, number_type in invalid_cases:
            with self.subTest(key=key):
                form_state = {
                    **base_state,
                    "variables": {key: raw},
                    "metadata": {
                        key: {"kind": "number", "number_type": number_type},
                    },
                }
                with self.assertRaisesRegex(ValueError, key.split(":", 1)[1]):
                    self.manager.collect_for_source("umbriel", form_state)

    def test_noctalia_choices_and_installed_palettes(self):
        palette_dir = Path(self.temp_dir.name, "community-palettes")
        palette_dir.mkdir()
        (palette_dir / "Oxocarbon.json").touch()
        (palette_dir / "Local-only.json").touch()
        with patch("config.NOCTALIA_COMMUNITY_PALETTE_DIR", str(palette_dir)):
            choices = self.manager.choices_for(
                "noctalia", "theme.community_palette", "Oxocarbon")
            self.assertIn("ADW", choices)
            self.assertIn("Atuel", choices)
            self.assertIn("Oxocarbon", choices)
            self.assertIn("Local-only", choices)
            self.assertEqual(
                choices,
                sorted(set(choices), key=str.casefold))
            self.assertIn(
                "Missing",
                self.manager.choices_for(
                    "noctalia", "theme.community_palette", "Missing"))
        self.assertEqual(
            self.manager.choices_for("noctalia", "dock.layer", "auto"),
            ["top", "overlay"])

    def test_manager_loads_source_and_schema_choices(self):
        source_spec = {
            "name": "Umbriel",
            "load_paths": [str(self.config_path)],
            "save_path": str(self.config_path),
        }
        schema = {
            "settings": [
                {"path": "input.focus.mode", "values": ["off", "always"]},
            ],
        }
        with (
                patch("config.SOURCES", {"umbriel": source_spec}),
                patch("config.fetch_noctalia_full_config", return_value=({}, [])),
                patch("config.fetch_umbriel_schema", return_value=schema)):
            manager = config.ConfigManager()

        self.assertIn("settings", manager.sources["umbriel"].merged)
        self.assertEqual(
            manager.choices_for("umbriel", "input.focus.mode", "off"),
            ["off", "always"])

    def test_category_sections_preserve_noctalia_default_markers(self):
        source_path = Path(self.temp_dir.name, "noctalia-settings.toml")
        source = config.ConfigSource(
            "noctalia",
            {
                "name": "Noctalia",
                "load_paths": [],
                "save_path": str(source_path),
            },
        )
        source.load()
        self.manager.sources["noctalia"] = source
        self.manager.noctalia_full_config = {
            "dock": {"enabled": True, "layer": "top"},
        }

        sections = self.manager.category_sections("noctalia", "Dock")

        self.assertEqual(
            sections[0], ("Dock", [("dock.enabled", True, True)]))
        self.assertEqual(
            sections[1],
            ("Noctalia · dock", [("dock.layer", "top", True)]))


if __name__ == "__main__":
    unittest.main()
