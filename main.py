#!/usr/bin/env python3
"""
Noctalia + Umbriel configuration GUI  (validate-before-save).

Sources
-------
Umbriel  :  ~/.config/umbriel/config.toml                      (read + write)
Noctalia :  ~/.config/noctalia/*.toml                          (read, merged
            ~/.local/state/noctalia/settings.toml               alphabetically)
                                                               (read + write:
                                                                override file)

Save pipeline (per source)
--------------------------
  1. Build merged config:   deep_merge(existing_file, GUI_state)
  2. Serialize to TOML text
  3. Self-parse (tomllib.loads) → abort on failure
  4. Write serialized text to a temporary ``.toml`` file
  5. Run official validator against that temp file:
         umbriel config validate -c <tmp> --json
         noctalia        config validate <tmp>
  6. If validator reports ERROR → message box, ABORT (real file untouched)
  7. On success (or warnings only) → back up real file, then write it

Requires Python 3.11+ (tomllib), or ``tomli`` on 3.10 and below.
"""

import glob
import io
import re
import json
import hashlib
import math
import datetime
import copy
import stat
import os
import shutil
import subprocess
import tempfile
import customtkinter as ctk
import tkinter as tk
from tkinter import ttk, filedialog, colorchooser, messagebox, simpledialog
from number_input import NumberInput

try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib
    except ImportError:
        tomllib = None


# ---------------------------------------------------------------------------
# Source definitions
# ---------------------------------------------------------------------------

def _labeled_frame(parent, text, padding=6):
    section = ctk.CTkFrame(parent)
    section.pack(fill="x", padx=6, pady=6)
    ctk.CTkLabel(
        section, text=text, anchor="w",
        font=ctk.CTkFont(weight="bold")).pack(
            fill="x", padx=padding, pady=(padding, 2))
    content = ctk.CTkFrame(section, fg_color="transparent")
    content.pack(fill="x", padx=padding, pady=(0, padding))
    return content


HOME = os.path.expanduser("~")
XDG_CONFIG_HOME = os.path.expanduser(
    os.environ.get("XDG_CONFIG_HOME", os.path.join(HOME, ".config")))
XDG_STATE_HOME = os.path.expanduser(
    os.environ.get("XDG_STATE_HOME", os.path.join(HOME, ".local", "state")))
NOCTALIA_CONFIG_DIR = os.path.join(
    os.path.expanduser(os.environ.get("NOCTALIA_CONFIG_HOME", XDG_CONFIG_HOME)),
    "noctalia")
NOCTALIA_STATE_DIR = os.path.join(
    os.path.expanduser(os.environ.get("NOCTALIA_STATE_HOME", XDG_STATE_HOME)),
    "noctalia")
UMBRIEL_CONFIG_DIR = os.path.join(XDG_CONFIG_HOME, "umbriel")

SOURCES = {
    "umbriel": {
        "name": "Umbriel",
        "load_globs": [],
        "load_paths": [os.path.join(UMBRIEL_CONFIG_DIR, "config.toml")],
        "save_path": os.path.join(UMBRIEL_CONFIG_DIR, "config.toml"),
    },
    "noctalia": {
        "name": "Noctalia",
        "load_globs": [os.path.join(NOCTALIA_CONFIG_DIR, "*.toml")],
        "load_paths": [os.path.join(NOCTALIA_STATE_DIR, "settings.toml")],
        "save_path": os.path.join(NOCTALIA_STATE_DIR, "settings.toml"),
    },
}

CATEGORY_SOURCES = {
    "Compositor (Umbriel)": ["umbriel"],
    "Configuration":        ["noctalia"],
    "Bar":                  ["umbriel", "noctalia"],
    "Dock":                 ["noctalia"],
    "Launcher":             ["noctalia"],
    "Theming":              ["umbriel", "noctalia"],
    "Desktop":              ["umbriel", "noctalia"],
    "Services":             ["noctalia"],
    "KeyBinding":           ["umbriel", "noctalia"],
    "More":                 ["umbriel", "noctalia"],
}

REPLACE_KEYS = {"keybinds", "window_rule", "layer_rule"}
DEFAULT_ANIMATION_CURVE = "easeout"

KEY_PREFIX_TO_CATEGORY = {
    "general": "Compositor (Umbriel)",
    "include": "Compositor (Umbriel)",
    "events": "Compositor (Umbriel)",
    "screencast": "Compositor (Umbriel)",
    "input": "Compositor (Umbriel)",
    "appearance.blur": "Theming",
    "appearance.title_bar": "Theming",
    "appearance.tab_bar": "Bar",
    "colors": "Theming",
    "layout": "More",
    "animation": "More",
    "effects": "More",
    "window_rule": "More",
    "layer_rule": "More",
    "hot_corners": "Desktop",
    "keybinds": "KeyBinding",
    "scratchpad": "More",
    "theme": "Theming",
    "wallpaper": "Desktop",
    "bar": "Bar",
    "dock": "Dock",
    "launcher": "Launcher",
    "shell.launcher": "Launcher",
    "shell.bar": "Bar",
    "shell.dock": "Dock",
    "audio": "Services",
    "bluetooth": "Services",
    "brightness": "Services",
    "calendar": "Services",
    "night_light": "Services",
    "nightlight": "Services",
    "idle": "Services",
    "weather": "Services",
    "battery": "Services",
    "notification": "Services",
    "accessibility": "More",
    "shell": "More",
    "config": "Configuration",
}


# ---------------------------------------------------------------------------
# Umbriel rich schema (used to render sliders/radios/colour pickers)
# ---------------------------------------------------------------------------
UMBRIEL_SCHEMA = {
    "Compositor (Umbriel)": {
        "Includes": [
            {"key": "include.files", "label": "Include Files",
             "type": "list", "item_type": "str", "default": []},
            {"key": "include.optional.files", "label": "Optional Include Files",
             "type": "list", "item_type": "str", "default": []},
        ],
        "General": [
            {"key": "general.autostart", "label": "Autostart Commands",
             "type": "list", "item_type": "str", "default": []},
            {"key": "general.xwayland", "label": "Enable XWayland",
             "type": "boolean", "default": True},
            {"key": "general.xwayland_native_resolution",
             "label": "XWayland Native Resolution",
             "type": "boolean", "default": False},
            {"key": "general.xwayland_xsettings",
             "label": "XWayland XSettings", "type": "boolean", "default": True},
            {"key": "general.xwayland_primary_output",
             "label": "XWayland Primary Output", "type": "text", "default": ""},
            {"key": "general.nvidia_sync_workaround",
             "label": "NVIDIA Sync Workaround",
             "type": "boolean", "default": True},
            {"key": "general.attach_modal_dialogs",
             "label": "Attach Modal Dialogs",
             "type": "boolean", "default": True},
        ],
        "Events": [
            {"key": "events.lid_close", "label": "Lid Close Command",
             "type": "text", "default": ""},
            {"key": "events.lid_open", "label": "Lid Open Command",
             "type": "text", "default": ""},
        ],
        "Screencast": [
            {"key": "screencast.disable_dynamic_confirmation",
             "label": "Disable Dynamic Confirmation",
             "type": "boolean", "default": False},
        ],
        "Input": [
            {"key": "input.keyboard.numlock_toggle",
             "label": "NumLock Toggle", "type": "boolean", "default": True},
            {"key": "input.focus.follows_mouse", "label": "Focus Follows Mouse",
             "type": "choice", "choices": ["off", "sloppy", "always"],
             "default": "off"},
            {"key": "input.focus.hover_raises", "label": "Hover Raises",
             "type": "boolean", "default": False},
            {"key": "input.touch.enabled", "label": "Touch Enabled",
             "type": "boolean", "default": False},
            {"key": "input.touch.map_to_output", "label": "Touch Map to Output",
             "type": "text", "default": ""},
        ],
    },
    "Bar": {
        "Umbriel · Tab Bar Appearance": [
            {"key": "appearance.tab_bar.style", "label": "Style",
             "type": "choice", "choices": ["titles", "indicator"],
             "default": "titles"},
            {"key": "appearance.tab_bar.height", "label": "Height (px)",
             "type": "slider", "min": 16, "max": 64, "default": 24},
            {"key": "appearance.tab_bar.gap", "label": "Gap (-1=layout.gap)",
             "type": "slider", "min": -1, "max": 32, "default": -1},
            {"key": "appearance.tab_bar.font", "label": "Font",
             "type": "text", "default": "sans 10"},
            {"key": "appearance.tab_bar.visible", "label": "Visible",
             "type": "boolean", "default": True},
            {"key": "appearance.tab_bar.hide_when_single",
             "label": "Hide When Single", "type": "boolean", "default": False},
            {"key": "appearance.tab_bar.max_tabs", "label": "Max Tabs",
             "type": "slider", "min": 1, "max": 32, "default": 6},
            {"key": "appearance.tab_bar.overflow", "label": "Overflow",
             "type": "choice", "choices": ["scroll", "shrink"],
             "default": "scroll"},
        ],
        "Umbriel · Tabs Behaviour": [
            {"key": "layout.tabs.default_display", "label": "Default Display",
             "type": "text", "default": "normal"},
            {"key": "layout.tabs.new_tab_position", "label": "New Tab Position",
             "type": "text", "default": "after_active"},
            {"key": "layout.tabs.middle_click_closes",
             "label": "Middle Click Closes", "type": "boolean", "default": True},
        ],
    },
    "Theming": {
        "Umbriel · Blur": [
            {"key": "appearance.blur.enabled", "label": "Enable Blur",
             "type": "boolean", "default": True},
            {"key": "appearance.blur.optimized", "label": "Optimized Blur",
             "type": "boolean", "default": True},
            {"key": "appearance.blur.passes", "label": "Blur Passes",
             "type": "slider", "min": 0, "max": 8, "default": 2},
            {"key": "appearance.blur.radius", "label": "Blur Radius",
             "type": "slider", "min": 0, "max": 100, "default": 5},
            {"key": "appearance.blur.noise", "label": "Blur Noise",
             "type": "slider", "min": 0.0, "max": 1.0, "default": 0.02},
            {"key": "appearance.blur.brightness", "label": "Blur Brightness",
             "type": "slider", "min": 0.0, "max": 2.0, "default": 0.9},
            {"key": "appearance.blur.contrast", "label": "Blur Contrast",
             "type": "slider", "min": 0.0, "max": 2.0, "default": 0.9},
            {"key": "appearance.blur.saturation", "label": "Blur Saturation",
             "type": "slider", "min": 0.0, "max": 2.0, "default": 1.1},
        ],
        "Umbriel · Window Appearance": [
            {"key": "appearance.prefer_no_csd",
             "label": "Prefer server-side decorations",
             "type": "boolean", "default": True},
            {"key": "appearance.border_width", "label": "Border Width",
             "type": "slider", "min": 0, "max": 100, "default": 2},
            {"key": "appearance.corner_radius", "label": "Corner Radius",
             "type": "slider", "min": 0, "max": 100, "default": 10},
        ],
        "Umbriel · Title Bar": [
            {"key": "appearance.title_bar.mode", "label": "Mode",
             "type": "choice",
             "choices": ["on", "negotiated", "forced", "off"],
             "default": "off"},
            {"key": "appearance.title_bar.height", "label": "Height (px)",
             "type": "slider", "min": 16, "max": 64, "default": 28},
            {"key": "appearance.title_bar.font", "label": "Font",
             "type": "text", "default": "sans 10"},
            {"key": "appearance.title_bar.title_align", "label": "Title Align",
             "type": "choice", "choices": ["left", "center", "right"],
             "default": "left"},
            {"key": "appearance.title_bar.button_position",
             "label": "Button Position",
             "type": "choice", "choices": ["left", "right"], "default": "right"},
            {"key": "appearance.title_bar.buttons", "label": "Buttons",
             "type": "list", "item_type": "str",
             "default": ["minimize", "maximize", "close"]},
            {"key": "appearance.title_bar.button_size",
             "label": "Button Size", "type": "slider",
             "min": -1, "max": 64, "default": -1},
            {"key": "appearance.title_bar.button_gap",
             "label": "Button Gap (px)", "type": "slider",
             "min": 0, "max": 32, "default": 8},
            {"key": "appearance.title_bar.button_padding",
             "label": "Button Padding", "type": "slider",
             "min": -1, "max": 32, "default": -1},
            {"key": "appearance.title_bar.button_corner_radius",
             "label": "Button Corner Radius", "type": "slider",
             "min": -1, "max": 32, "default": -1},
            {"key": "appearance.title_bar.button_glyph",
             "label": "Button Glyph", "type": "choice",
             "choices": ["always", "hover", "never"], "default": "hover"},
            {"key": "appearance.title_bar.button_glyph_size",
             "label": "Glyph Size", "type": "slider",
             "min": -1, "max": 128, "default": -1},
            {"key": "appearance.title_bar.button_glyph_stroke",
             "label": "Glyph Stroke", "type": "slider",
             "min": -1, "max": 16, "default": -1},
            {"key": "appearance.title_bar.button_background",
             "label": "Button Background", "type": "boolean", "default": True},
        ],
        "Umbriel · Title Bar Colours": [
            {"key": "colors.backdrop", "label": "Lock-screen Backdrop",
             "type": "color", "default": "#000000FF"},
            {"key": "colors.title_bar.close", "label": "Close Button",
             "type": "color", "default": "#FF6B6BFF"},
            {"key": "colors.title_bar.close_glyph", "label": "Close Glyph",
             "type": "color", "default": "#141419FF"},
            {"key": "colors.title_bar.close_glyph_hover",
             "label": "Close Glyph Hover",
             "type": "color", "default": "#141419FF"},
            {"key": "colors.title_bar.maximize", "label": "Maximize Button",
             "type": "color", "default": "#7AA3FFFF"},
            {"key": "colors.title_bar.maximize_glyph", "label": "Maximize Glyph",
             "type": "color", "default": "#141419FF"},
            {"key": "colors.title_bar.maximize_glyph_hover",
             "label": "Maximize Glyph Hover",
             "type": "color", "default": "#141419FF"},
            {"key": "colors.title_bar.minimize", "label": "Minimize Button",
             "type": "color", "default": "#FFD166FF"},
            {"key": "colors.title_bar.minimize_glyph", "label": "Minimize Glyph",
             "type": "color", "default": "#141419FF"},
            {"key": "colors.title_bar.minimize_glyph_hover",
             "label": "Minimize Glyph Hover",
             "type": "color", "default": "#141419FF"},
        ],
    },
    "Desktop": {
        "Umbriel · Hot Corner (Top-Left)": [
            {"key": "hot_corners.top_left.enabled", "label": "Enabled",
             "type": "boolean", "default": True},
            {"key": "hot_corners.top_left.delay_ms", "label": "Delay (ms)",
             "type": "slider", "min": 0, "max": 2000, "default": 500},
            {"key": "hot_corners.top_left.action", "label": "Action",
             "type": "text", "default": "overview-open"},
        ],
    },
    "KeyBinding": None,
    "More": {
        "Umbriel · Layout": [
            {"key": "layout.mode", "label": "Mode", "type": "choice",
             "choices": ["scrolling", "dwindle", "master", "stacking"],
             "default": "scrolling"},
            {"key": "layout.extent_presets", "label": "Extent Presets",
             "type": "list", "item_type": "float",
             "default": [0.333, 0.5, 0.667]},
            {"key": "layout.client_maximize", "label": "Client Maximize",
             "type": "choice", "choices": ["column", "edges"],
             "default": "column"},
            {"key": "layout.scrolling.default_extent_fraction",
             "label": "Default Extent Fraction",
             "type": "slider", "min": 0.1, "max": 1.0,
             "default": 0.5, "resolution": 0.05},
            {"key": "layout.scrolling.center_on_overview_select",
             "label": "Center on Overview Select",
             "type": "boolean", "default": False},
            {"key": "layout.stacking.drop_zones", "label": "Stacking Drop Zones",
             "type": "boolean", "default": True},
        ],
        "Umbriel · Effects": [
            {"key": "effects.border", "label": "Border Effect Name",
             "type": "text", "default": ""},
            {"key": "effects.border_unfocused", "label": "Border on Unfocused",
             "type": "boolean", "default": False},
        ],
        "Umbriel · Animation": [
            {"key": "animation.windows_opacity.enabled",
             "label": "Window Opacity Anim", "type": "boolean", "default": True},
            {"key": "animation.windows_opacity.curve", "label": "Opacity Curve",
             "type": "text", "default": DEFAULT_ANIMATION_CURVE},
            {"key": "animation.windows_opacity.duration_ms",
             "label": "Opacity Duration (ms)", "type": "slider",
             "min": 0, "max": 2000, "default": 250},
            {"key": "animation.windows_resize.enabled",
             "label": "Window Resize Anim", "type": "boolean", "default": False},
            {"key": "animation.windows_resize.wait_for_redraw",
             "label": "Wait for Redraw", "type": "boolean", "default": True},
            {"key": "animation.workspaces.style", "label": "Workspaces Style",
             "type": "choice", "choices": ["slide", "reveal"],
             "default": "slide"},
            {"key": "animation.workspaces.effect", "label": "Workspaces Effect",
             "type": "text", "default": ""},
            {"key": "animation.workspaces.duration_ms",
             "label": "Workspaces Duration (ms)", "type": "slider",
             "min": 0, "max": 2000, "default": 300},
            {"key": "animation.workspaces.curve", "label": "Workspaces Curve",
             "type": "text", "default": "easeout"},
            {"key": "animation.dialogs.dim", "label": "Dialog Dim",
             "type": "slider", "min": 0.0, "max": 1.0,
             "default": 0.3, "resolution": 0.05},
        ],
        "Umbriel · Window Rules (raw TOML)": [
            {"key": "window_rule", "label": "[[window_rule]] blocks",
             "type": "raw_aot", "default": []},
        ],
        "Umbriel · Layer Rules (raw TOML)": [
            {"key": "layer_rule", "label": "[[layer_rule]] blocks",
             "type": "raw_aot", "default": []},
        ],
    },
}


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------
def deep_merge(base, overlay, replace_keys=frozenset()):
    for k, v in overlay.items():
        if k in replace_keys:
            base[k] = v
        elif isinstance(v, dict) and isinstance(base.get(k), dict):
            deep_merge(base[k], v, replace_keys)
        else:
            base[k] = v
    return base


def iter_leaf_entries(cfg, prefix=""):
    for k, v in cfg.items():
        full = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            yield from iter_leaf_entries(v, full)
        else:
            yield full, v


def categorize_key(source_name, key):
    if source_name == "noctalia" and (
            key == "include" or key.startswith("include.")):
        return "Configuration"
    for prefix, cat in KEY_PREFIX_TO_CATEGORY.items():
        if key == prefix or key.startswith(prefix + "."):
            return cat
    return "More"


def infer_kind(value):
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "color" if _looks_like_hex_color(value) else "text"
    if isinstance(value, list):
        if value and all(isinstance(x, dict) for x in value):
            return "aot"
        return "list"
    if isinstance(value, dict):
        return "table"
    return "text"


def _looks_like_hex_color(s):
    if not s.startswith("#"):
        return False
    body = s[1:]
    return len(body) in (6, 8) and all(c in "0123456789abcdefABCDEF" for c in body)


def _color_preview(hex_rgba):
    try:
        h = hex_rgba.lstrip("#")
        return "#" + (h[:6] if len(h) == 8 else h)
    except Exception:
        return "#000000"


def _get_dotted(cfg, key):
    cur = cfg
    for part in key.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _set_dotted(cfg, key, value):
    parts = key.split(".")
    d = cfg
    for p in parts[:-1]:
        d = d.setdefault(p, {})
        if not isinstance(d, dict):
            return
    d[parts[-1]] = value


def _delete_dotted(cfg, key):
    parts = key.split(".")
    parents = []
    current = cfg
    for part in parts[:-1]:
        if not isinstance(current, dict) or part not in current:
            return
        parents.append((current, part))
        current = current[part]
    if not isinstance(current, dict) or parts[-1] not in current:
        return
    del current[parts[-1]]
    for parent, part in reversed(parents):
        child = parent[part]
        if not isinstance(child, dict) or child:
            break
        del parent[part]


def _parse_kb_options(text):
    opts = {}
    for part in text.split(","):
        part = part.strip()
        if not part or "=" not in part:
            continue
        k, v = part.split("=", 1)
        k, v = k.strip(), v.strip()
        if v.lower() == "true":
            opts[k] = True
        elif v.lower() == "false":
            opts[k] = False
        elif v.startswith('"') and v.endswith('"'):
            opts[k] = v[1:-1]
        else:
            try:
                opts[k] = int(v)
            except ValueError:
                try:
                    opts[k] = float(v)
                except ValueError:
                    opts[k] = v
    return opts


# ---------------------------------------------------------------------------
# TOML writer
# ---------------------------------------------------------------------------
def toml_key(k):
    if k and all(c.isalnum() or c in "-_" for c in k):
        return k
    return '"' + k.replace('"', '\\"') + '"'



def toml_value(v):
    """Serialize Python TOML values without losing whitespace/control chars."""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, str):
        # JSON basic-string escaping is compatible with TOML basic strings.
        return json.dumps(v, ensure_ascii=False)
    if isinstance(v, datetime.datetime):
        return v.isoformat()
    if isinstance(v, (datetime.date, datetime.time)):
        return v.isoformat()
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        if math.isnan(v):
            return "nan"
        if math.isinf(v):
            return "inf" if v > 0 else "-inf"
        return repr(v)
    if isinstance(v, list):
        return "[" + ", ".join(toml_value(x) for x in v) + "]"
    if isinstance(v, dict):
        return toml_inline_table(v)
    raise TypeError(f"Unsupported TOML value: {type(v).__name__}")


def toml_inline_table(d):
    parts = [f"{toml_key(k)} = {toml_value(v)}" for k, v in d.items()]
    return "{ " + ", ".join(parts) + " }"


def _toml_table_path(parts):
    return ".".join(toml_key(str(p)) for p in parts)


def _write_toml_body(f, obj, prefix=(), in_aot=False):
    """Write TOML tables/AoT recursively, preserving insertion order."""
    if not isinstance(obj, dict):
        return
    scalar, tables, aots = [], [], []
    for k, v in obj.items():
        if isinstance(v, dict):
            # keybinds values are compositor-specific inline option tables.
            if prefix == ("keybinds",) or in_aot:
                scalar.append((k, v))
            else:
                tables.append((k, v))
        elif isinstance(v, list) and v and all(isinstance(x, dict) for x in v):
            aots.append((k, v))
        else:
            scalar.append((k, v))

    for k, v in scalar:
        f.write(f"{toml_key(str(k))} = {toml_value(v)}\n")

    for k, arr in aots:
        section = prefix + (str(k),)
        for item in arr:
            f.write(f"\n[[{_toml_table_path(section)}]]\n")
            _write_toml_body(f, item, section, in_aot=True)

    for k, sub in tables:
        section = prefix + (str(k),)
        f.write(f"\n[{_toml_table_path(section)}]\n")
        _write_toml_body(f, sub, section)


def to_toml_string(obj):
    buf = io.StringIO()
    buf.write("# Written by Noctalia/Umbriel config GUI\n\n")
    _write_toml_body(buf, obj)
    return buf.getvalue()


def serialize_aot(key, items):
    """Serialize an array of tables using the same safe TOML writer."""
    buf = io.StringIO()
    section = tuple(key.split("."))
    for item in items:
        buf.write(f"[[{_toml_table_path(section)}]]\n")
        _write_toml_body(buf, item, section, in_aot=True)
        buf.write("\n")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Official validator wrapper
# ---------------------------------------------------------------------------
def run_official_validator(source_key, temp_file):
    """Validate a temp file with the real ``umbriel`` / ``noctalia`` binary.

    Returns dict:
      installed  – False if the binary isn't on PATH
      ok         – True if validation found no errors (warnings are allowed)
      diagnostics– list of dicts (severity/message/file/line/column)
      raw        – combined stdout/stderr (for display)
    """
    if source_key == "umbriel":
        # -c must follow `config validate`; a leading -c launches the compositor.
        cmd = ["umbriel", "config", "validate", "-c", temp_file, "--json"]
    else:
        cmd = ["noctalia", "config", "validate", temp_file]

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except FileNotFoundError:
        return {"installed": False, "ok": False, "diagnostics": [],
                "raw": f"{cmd[0]} not found on PATH"}
    except subprocess.TimeoutExpired:
        return {"installed": True, "ok": False, "diagnostics": [],
                "raw": "validator timed out after 30s"}

    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    combined = (out + ("\n" + err if err else "")).strip()
    diagnostics = []

    if source_key == "umbriel":
        # Prefer JSON (documented for both binary versions)
        try:
            payload = json.loads(out) if out else {}
            diagnostics = payload.get("diagnostics", []) or []
            # Umbriel reports valid=false and exits 1 even for warnings only.
            has_error = any(str(d.get("severity", "")).lower() == "error"
                            for d in diagnostics)
            if diagnostics:
                valid = not has_error
            else:
                valid = bool(payload.get("valid", proc.returncode == 0)) \
                    and proc.returncode == 0
            return {"installed": True,
                    "ok": valid,
                    "diagnostics": diagnostics, "raw": combined}
        except json.JSONDecodeError:
            pass  # fall through to text parsing

    # Text mode (Noctalia, or old Umbriel without --json)
    for line in combined.splitlines():
        line = line.strip()
        if not line:
            continue
        up = line.upper()
        if up.startswith("ERROR"):
            diagnostics.append({"severity": "error", "message": line})
        elif up.startswith("WARN"):
            diagnostics.append({"severity": "warning", "message": line})

    return {"installed": True,
            "ok": proc.returncode == 0,
            "diagnostics": diagnostics,
            "raw": combined}


def format_diagnostics(diags, raw):
    if not diags:
        return raw or "(no diagnostics reported)"
    lines = []
    for d in diags:
        sev = (d.get("severity") or "?").upper()
        loc = ""
        f = d.get("file")
        if f:
            loc = (f"{f}:{d.get('line', '?')}:"
                   f"{d.get('column', '?')}: ")
        lines.append(f"[{sev}] {loc}{d.get('message', '')}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Config source (load + prepare-write; write only after validation)
# ---------------------------------------------------------------------------

class ExternalChange(RuntimeError):
    """The target file was modified by another program since it was loaded."""


class ConfigSource:
    loaded_data = None

    def __init__(self, key, spec):
        self.key = key
        self.name = spec["name"]
        self.load_globs = spec.get("load_globs", [])
        self.load_paths = spec.get("load_paths", [])
        self.save_path = spec["save_path"]
        self.merged = {}
        self.per_file = {}
        self.load_errors = []
        self.loaded_fingerprint = self._fingerprint()

    def _fingerprint(self):
        try:
            with open(self.save_path, "rb") as f:
                return hashlib.sha256(f.read()).hexdigest()
        except FileNotFoundError:
            return None

    def resolve_load_paths(self):
        paths = []
        for pattern in self.load_globs:
            paths.extend(sorted(glob.glob(pattern)))
        for path in self.load_paths:
            if path not in paths:
                paths.append(path)
        return paths

    def load(self):
        self.merged, self.per_file, self.load_errors = {}, {}, []
        for path in self.resolve_load_paths():
            if not os.path.exists(path):
                continue
            try:
                with open(path, "rb") as f:
                    data = tomllib.load(f)
                self.per_file[path] = data
                deep_merge(self.merged, data)
            except Exception as exc:
                self.load_errors.append(f"{path}: {exc}")
        self.loaded_fingerprint = self._fingerprint()
        try:
            self.loaded_data = self.read_disk()
        except RuntimeError:
            self.loaded_data = None
        return self.merged

    def read_disk(self):
        if not os.path.exists(self.save_path):
            return {}
        try:
            with open(self.save_path, "rb") as f:
                return tomllib.load(f)
        except Exception as exc:
            raise RuntimeError(f"Could not parse {self.save_path}: {exc}")

    def prepare_text(self, gui_cfg, remove_keys=()):
        base = self.read_disk()
        for key in remove_keys:
            _delete_dotted(base, key)
        merged = deep_merge(base, gui_cfg, REPLACE_KEYS)
        return to_toml_string(merged)

    def commit(self, text):
        """Atomic write with mandatory backup and optimistic concurrency check."""
        os.makedirs(os.path.dirname(self.save_path) or ".", exist_ok=True)
        current = self._fingerprint()
        if current != self.loaded_fingerprint:
            # Programs such as Noctalia rewrite their state file right after
            # a save (reformatting only). Only treat it as a conflict when the
            # parsed content really differs from what we last saw.
            try:
                same = self.read_disk() == self.loaded_data
            except RuntimeError:
                same = False
            if not same:
                raise ExternalChange(
                    "The file changed on disk after it was loaded.")
            self.loaded_fingerprint = current

        old_exists = os.path.exists(self.save_path)
        old_mode = stat.S_IMODE(os.stat(self.save_path).st_mode) if old_exists else 0o600
        if old_exists:
            backup = self.save_path + ".bak"
            shutil.copy2(self.save_path, backup)

        fd, temp_path = tempfile.mkstemp(
            prefix=".config-gui-", suffix=".tmp",
            dir=os.path.dirname(self.save_path) or "."
        )
        try:
            os.chmod(temp_path, old_mode)
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
                f.write(text)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_path, self.save_path)
            self.loaded_fingerprint = self._fingerprint()
            self.loaded_data = tomllib.loads(text)
        except Exception:
            try:
                os.unlink(temp_path)
            except OSError:
                pass
            raise


def fetch_umbriel_schema():
    """Return schema JSON from the installed Umbriel binary, or a clear error."""
    try:
        proc = subprocess.run(
            ["umbriel", "config", "schema", "--json"],
            capture_output=True, text=True, timeout=15
        )
    except FileNotFoundError:
        raise RuntimeError("`umbriel` was not found on PATH.")
    except subprocess.TimeoutExpired:
        raise RuntimeError("Umbriel schema query timed out after 15 seconds.")
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or
                            f"Umbriel exited with status {proc.returncode}").strip())
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Umbriel returned invalid schema JSON: {exc}")


def _normalize_toml_11(text):
    """Rewrite common TOML 1.1 constructs into TOML 1.0 for ``tomllib``.

    * newlines / comments inside inline tables  -> collapsed onto one line
    * trailing comma before ``}``               -> removed
    * ``\\e`` and ``\\xHH`` escapes              -> ``\\u001b`` / ``\\u00HH``
    """
    out, i, n, stack = [], 0, len(text), []
    while i < n:
        c = text[i]
        if text.startswith('"""', i) or text.startswith("'''", i):
            q = text[i:i + 3]
            j = i + 3
            while j < n and not text.startswith(q, j):
                j += 2 if (q == '"""' and text[j] == "\\") else 1
            j = min(j + 3, n)
            out.append(text[i:j])
            i = j
        elif c == '"':
            j = i + 1
            buf = ['"']
            while j < n and text[j] != '"' and text[j] != "\n":
                if text[j] == "\\" and j + 1 < n:
                    nxt = text[j + 1]
                    if nxt == "e":
                        buf.append("\\u001b"); j += 2; continue
                    if nxt == "x" and j + 3 < n:
                        buf.append("\\u00" + text[j + 2:j + 4]); j += 4; continue
                    buf.append(text[j:j + 2]); j += 2; continue
                buf.append(text[j]); j += 1
            if j < n and text[j] == '"':
                buf.append('"'); j += 1
            out.append("".join(buf))
            i = j
        elif c == "'":
            j = i + 1
            while j < n and text[j] not in "'\n":
                j += 1
            j = min(j + 1, n)
            out.append(text[i:j])
            i = j
        elif c == "#":
            j = text.find("\n", i)
            j = n if j == -1 else j
            if "{" not in stack:
                out.append(text[i:j])
            i = j
        elif c in "{[":
            stack.append(c); out.append(c); i += 1
        elif c in "}]":
            if c == "}":
                while out and not out[-1].strip():
                    out.pop()
                if out and out[-1] == ",":
                    out.pop()
            if stack:
                stack.pop()
            out.append(c); i += 1
        elif c == "\n" and "{" in stack:
            out.append(" "); i += 1
        else:
            out.append(c); i += 1
    return "".join(out)


_TOML_HEADER_RE = re.compile(
    r"""^\s*\[\[?\s*[A-Za-z0-9_\-."' ]+\s*\]\]?\s*(#.*)?$""")


def _merge_lenient(base, new):
    """Merge a parsed chunk into ``base``; arrays of tables are appended."""
    for k, v in new.items():
        cur = base.get(k)
        if isinstance(cur, dict) and isinstance(v, dict):
            _merge_lenient(cur, v)
        elif isinstance(cur, list) and cur and isinstance(v, dict):
            if isinstance(cur[-1], dict):
                _merge_lenient(cur[-1], v)
        elif (isinstance(cur, list) and isinstance(v, list)
              and v and all(isinstance(x, dict) for x in v)):
            cur.extend(v)
        else:
            base[k] = v


def _toml_error_context(text, exc, radius=2):
    m = re.search(r"line (\d+)", str(exc))
    if not m:
        return str(exc)
    ln = int(m.group(1))
    lines = text.splitlines()
    lo, hi = max(0, ln - 1 - radius), min(len(lines), ln + radius)
    snippet = "\n".join(
        f"{'>' if i + 1 == ln else ' '} {i + 1:4}: {lines[i]}"
        for i in range(lo, hi))
    return f"{exc}\n{snippet}"


def parse_toml_lenient(text):
    """Parse TOML, tolerating TOML 1.1 syntax and isolated bad sections.

    Returns ``(config | None, warnings, error_text)``.
    """
    try:
        return tomllib.loads(text), [], None
    except Exception as first_exc:
        first_error = _toml_error_context(text, first_exc)

    normalized = _normalize_toml_11(text)
    try:
        return tomllib.loads(normalized), [], None
    except Exception:
        pass

    # Section-by-section salvage: a bad table no longer aborts everything.
    chunks, header, body = [], None, []
    for line in normalized.splitlines():
        if _TOML_HEADER_RE.match(line):
            chunks.append((header, body))
            header, body = line, []
        else:
            body.append(line)
    chunks.append((header, body))

    config, warnings = {}, []
    for header, body in chunks:
        chunk_text = ("\n".join(([header] if header else []) + body)).strip()
        if not chunk_text:
            continue
        try:
            _merge_lenient(config, tomllib.loads(chunk_text))
            continue
        except Exception as exc:
            chunk_err = str(exc)
        # Retry line by line inside this section.
        kept = 0
        for line in body:
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            try:
                _merge_lenient(config, tomllib.loads(
                    "\n".join(([header] if header else []) + [line])))
                kept += 1
            except Exception:
                warnings.append(
                    f"skipped in {header.strip() if header else '(root)'}: "
                    f"{s[:80]}")
        if kept == 0 and header:
            warnings.append(f"section {header.strip()} not parsed: {chunk_err}")
    if config:
        return config, warnings, None
    return None, warnings, first_error


def fetch_noctalia_full_config():
    """Return (config, warnings) for Noctalia's full effective config."""
    try:
        proc = subprocess.run(
            ["noctalia", "config", "export", "full", "--credentials", "omit"],
            capture_output=True, text=True, timeout=15
        )
    except FileNotFoundError:
        raise RuntimeError("`noctalia` was not found on PATH.")
    except subprocess.TimeoutExpired:
        raise RuntimeError("Noctalia config export timed out after 15 seconds.")
    except OSError as exc:
        raise RuntimeError(f"Could not run Noctalia config export: {exc}")
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or
                            f"Noctalia exited with status {proc.returncode}").strip())
    config, warnings, error = parse_toml_lenient(proc.stdout)
    if config is None:
        raise RuntimeError(f"Noctalia returned invalid TOML config: {error}")
    if not isinstance(config, dict) or not config:
        raise RuntimeError("Noctalia returned an empty config.")
    return config, warnings


CHOICE_RADIO_MAX = 5   # up to this many options -> radio buttons, else combobox

# Used only when the current value is one of the listed options.
KNOWN_CHOICES = {
    "position": ["top", "bottom", "left", "right"],
    "orientation": ["horizontal", "vertical"],
    "align": ["left", "center", "right"],
    "alignment": ["left", "center", "right"],
    "title_align": ["left", "center", "right"],
    "layer": ["top", "overlay", "auto"],
}

# The 28 palette roles from https://docs.noctalia.dev/noctalia/theming/palette/
# (UI colour settings accept one of these or a fixed hex colour).
NOCTALIA_COLOR_ROLES = [
    "primary", "on_primary", "primary_container", "on_primary_container",
    "secondary", "on_secondary", "secondary_container",
    "on_secondary_container", "tertiary", "on_tertiary",
    "tertiary_container", "on_tertiary_container", "error", "on_error",
    "error_container", "on_error_container", "surface", "on_surface",
    "on_surface_variant", "surface_container_low", "surface_container",
    "surface_container_high", "surface_container_highest",
    "outline_variant", "shadow", "scrim", "hover", "on_hover",
]


def _schema_value_choices(row):
    vals = row.get("values")
    if isinstance(vals, str) and vals.strip():
        vals = re.split(r"[|,]", vals)
    if not isinstance(vals, list):
        return None
    items = []
    for v in vals:
        if isinstance(v, dict):
            v = v.get("value", v.get("name"))
        if isinstance(v, str) and v.strip().strip("\"'"):
            items.append(v.strip().strip("\"'"))
    return items if len(items) >= 2 else None


def _path_regex(path):
    parts = re.split(r"<[^>]*>|\[\]", path)
    return re.compile("^" + "[^.]+".join(re.escape(p) for p in parts) + "$")


def flatten_schema(schema):
    """Normalize the documented schema JSON into rows for the explorer."""
    rows = []
    def walk(node, path_hint=""):
        if isinstance(node, list):
            for item in node:
                walk(item, path_hint)
        elif isinstance(node, dict):
            path = node.get("path") or node.get("key") or node.get("name")
            if isinstance(path, str) and path:
                rows.append({
                    "path": path,
                    "type": node.get("type", "unknown"),
                    "default": node.get("default", ""),
                    "range": node.get("range", ""),
                    "values": node.get("values", node.get("accepted_values", "")),
                    "format": node.get("format", ""),
                    "description": node.get("description", node.get("doc", "")),
                    "deprecated": bool(node.get("deprecated", False)),
                })
            else:
                for key, value in node.items():
                    if isinstance(value, (dict, list)):
                        walk(value, f"{path_hint}.{key}".strip("."))
    walk(schema)
    # Remove duplicates while retaining the last complete representation.
    unique = {}
    for row in rows:
        unique[row["path"]] = row
    return sorted(unique.values(), key=lambda r: r["path"].casefold())


# ---------------------------------------------------------------------------
# Main app
# ---------------------------------------------------------------------------
class App:
    def __init__(self, root):
        self.root = root
        self.root.title("Noctalia + Umbriel Configuration")
        self.root.geometry("1020x780")

        if tomllib is None:
            messagebox.showerror(
                "TOML support missing",
                "Install `tomli` for Python ≤ 3.10, or use Python 3.11+.")
            root.destroy()
            return

        self.sources = {k: ConfigSource(k, v) for k, v in SOURCES.items()}
        for src in self.sources.values():
            src.load()
        self.noctalia_parse_warnings = []
        try:
            (self.noctalia_full_config,
             self.noctalia_parse_warnings) = fetch_noctalia_full_config()
            self.noctalia_full_config_error = None
        except RuntimeError as exc:
            self.noctalia_full_config = {}
            self.noctalia_full_config_error = str(exc)

        # Accepted-value lists from the live Umbriel schema (for radios/combos)
        self.schema_choice_rules = []
        try:
            for r in flatten_schema(fetch_umbriel_schema()):
                ch = _schema_value_choices(r)
                if ch:
                    self.schema_choice_rules.append(
                        (_path_regex(r["path"]), ch))
        except Exception:
            pass

        self.vars = {}
        self.var_meta = {}
        self.raw_widgets = {}
        self.keybind_rows = []
        self.keybind_iids = {}
        self.dynamic_schema_edits = {}

        self.notebook = ctk.CTkTabview(root)
        self.notebook.pack(fill="both", expand=True, padx=5, pady=5)

        self._build_all_tabs()

        bar = ctk.CTkFrame(root, fg_color="transparent")
        bar.pack(fill="x", padx=5, pady=(0, 4))
        ctk.CTkButton(
            bar, text="Save All", command=self._save_all).pack(side="right")
        ctk.CTkButton(
            bar, text="Validate All (no save)",
            command=self._validate_all).pack(side="right", padx=4)
        ctk.CTkButton(
            bar, text="Reload", command=self._reload_all).pack(side="left")
        ctk.CTkButton(
            bar, text="Umbriel Schema Explorer",
            command=self._open_schema_explorer).pack(side="left", padx=6)

        self.status = ctk.CTkLabel(root, anchor="w")
        self.status.pack(fill="x", side="bottom")
        self._set_status(self._describe_loaded())

    # ------------------------------------------------------------------
    def _open_schema_explorer(self):
        win = ctk.CTkToplevel(self.root)
        win.title("Umbriel Configuration Schema Explorer")
        win.geometry("1050x680")
        top = ctk.CTkFrame(win, fg_color="transparent")
        top.pack(fill="x", padx=8, pady=8)
        ctk.CTkLabel(
            top,
            text="Live schema from the installed Umbriel binary "
                 "(umbriel config schema --json)"
        ).pack(side="left")
        status = ctk.CTkLabel(win, text="Loading schema…", anchor="w")
        status.pack(fill="x", padx=8, pady=(0, 4))

        body = ctk.CTkFrame(win, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=8, pady=4)
        columns = ("type", "default", "range", "values", "status")
        tree = ttk.Treeview(body, columns=columns, show="tree headings")
        tree.heading("#0", text="Configuration key")
        tree.column("#0", width=350)
        for col, title, width in (
            ("type", "Type", 100), ("default", "Default", 140),
            ("range", "Range", 130), ("values", "Accepted values", 220),
            ("status", "Current config", 120)
        ):
            tree.heading(col, text=title)
            tree.column(col, width=width)
        ysb = ttk.Scrollbar(body, orient="vertical", command=tree.yview)
        xsb = ttk.Scrollbar(body, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=ysb.set, xscrollcommand=xsb.set)
        tree.grid(row=0, column=0, sticky="nsew")
        ysb.grid(row=0, column=1, sticky="ns")
        xsb.grid(row=1, column=0, sticky="ew")
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)

        details = ctk.CTkTextbox(win, height=120, wrap="word", state="disabled")
        details.pack(fill="x", padx=8, pady=(0, 8))

        rows_by_iid = {}
        def show_details(_event=None):
            selection = tree.selection()
            if not selection:
                return
            row = rows_by_iid.get(selection[0], {})
            lines = [
                f"Key: {row.get('path', '')}",
                f"Type: {row.get('type', 'unknown')}",
                f"Default: {row.get('default', '')}",
                f"Range: {row.get('range', '')}",
                f"Accepted values: {row.get('values', '')}",
                f"Format: {row.get('format', '')}",
            ]
            if row.get("description"):
                lines.append(f"Description: {row['description']}")
            if row.get("deprecated"):
                lines.append("WARNING: This key is marked deprecated by the schema.")
            details.configure(state="normal")
            details.delete("1.0", "end")
            details.insert("1.0", "\n".join(lines))
            details.configure(state="disabled")
        tree.bind("<<TreeviewSelect>>", show_details)

        def refresh():
            status.configure(text="Querying installed Umbriel schema…")
            win.update_idletasks()
            try:
                payload = fetch_umbriel_schema()
                rows = flatten_schema(payload)
                if not rows:
                    raise RuntimeError(
                        "Schema JSON was valid, but no key entries with a `path` "
                        "field were found. The installed CLI may use a different schema format."
                    )
                tree.delete(*tree.get_children())
                rows_by_iid.clear()
                cfg = self.sources["umbriel"].merged
                for row in rows:
                    current = self.dynamic_schema_edits.get(
                        row["path"], _get_dotted(cfg, row["path"]))
                    current_status = "pending edit" if row["path"] in self.dynamic_schema_edits else (
                        "configured" if current is not None else "not set")
                    if row.get("deprecated"):
                        current_status = "deprecated"
                    iid = tree.insert(
                        "", "end", text=row["path"],
                        values=(
                            row.get("type", "unknown"),
                            json.dumps(row.get("default"), ensure_ascii=False)
                                if row.get("default") != "" else "",
                            json.dumps(row.get("range"), ensure_ascii=False)
                                if row.get("range") not in ("", None) else "",
                            json.dumps(row.get("values"), ensure_ascii=False)
                                if row.get("values") not in ("", None) else "",
                            current_status
                        )
                    )
                    rows_by_iid[iid] = row
                known = {row["path"] for row in rows}
                aot_roots = {
                    path.split("[]", 1)[0]
                    for path in known if "[]" in path
                }
                for key, value in iter_leaf_entries(cfg):
                    if key in known or key in aot_roots:
                        continue
                    unknown_row = {
                        "path": key, "type": infer_kind(value), "default": "",
                        "range": "", "values": "",
                        "description": "Present in the current configuration but not listed by the installed Umbriel schema.",
                        "unsupported": True
                    }
                    iid = tree.insert(
                        "", "end", text=key,
                        values=(unknown_row["type"], "", "", "", "unknown key"),
                        tags=("unknown",)
                    )
                    rows_by_iid[iid] = unknown_row
                tree.tag_configure("unknown", foreground="#b06020")
                version = payload.get("version", "unknown") if isinstance(payload, dict) else "unknown"
                revision = payload.get("revision", "unknown") if isinstance(payload, dict) else "unknown"
                status.configure(
                    text=f"{len(rows)} schema keys · Umbriel {version} · "
                         f"revision {revision}")
            except Exception as exc:
                status.configure(text=f"Schema unavailable: {exc}")
                messagebox.showerror("Schema Explorer", str(exc), parent=win)

        def edit_selected():
            selection = tree.selection()
            if not selection:
                messagebox.showinfo("Schema Explorer", "Select a schema key first.", parent=win)
                return
            row = rows_by_iid.get(selection[0])
            if not row:
                messagebox.showinfo(
                    "Schema Explorer",
                    "This key is not part of the installed schema and cannot be edited here.",
                    parent=win)
                return
            key = row["path"]
            if "<" in key or "[]" in key:
                messagebox.showinfo(
                    "Schema template",
                    "This is a schema template path. Replace its placeholder with a "
                    "real output name or array entry in the relevant configuration section.",
                    parent=win)
                return
            current = self.dynamic_schema_edits.get(
                key, _get_dotted(self.sources["umbriel"].merged, key))
            if current is None:
                current = row.get("default")
            initial = toml_value(current) if current is not None else ""
            literal = simpledialog.askstring(
                "Set Umbriel value",
                f"Enter a TOML value for {key} (e.g. true, 42, \"text\", [\"a\", \"b\"]):",
                initialvalue=initial, parent=win)
            if literal is None:
                return
            try:
                parsed = tomllib.loads("value = " + literal)["value"]
            except Exception as exc:
                messagebox.showerror("Invalid TOML value", str(exc), parent=win)
                return
            self.dynamic_schema_edits[key] = parsed
            status.configure(
                text=f"Pending edit: {key} = {toml_value(parsed)}. "
                     "Save All to write it.")
            show_details()
        ctk.CTkButton(
            top, text="Edit selected key…", command=edit_selected).pack(
                side="right", padx=5)
        ctk.CTkButton(
            top, text="Refresh schema", command=refresh).pack(side="right")
        refresh()

    # ------------------------------------------------------------------
    def _describe_loaded(self):
        bits = []
        for s in self.sources.values():
            label = f"{s.name}: {len(s.per_file)} file(s) → {s.save_path}"
            if s.load_errors:
                label += f"  ⚠ {len(s.load_errors)} load error(s)"
            bits.append(label)
        if self.noctalia_full_config_error:
            bits.append("Noctalia full config unavailable")
        return "   |   ".join(bits)

    # ------------------------------------------------------------------
    # Tab building
    # ------------------------------------------------------------------
    def _build_all_tabs(self):
        for category, sections in UMBRIEL_SCHEMA.items():
            self.notebook.add(category)
            tab = self.notebook.tab(category)
            if category == "KeyBinding":
                self._build_keybind_tab(tab)
            else:
                self._build_category_tab(tab, category, sections or {})

        defined = set(UMBRIEL_SCHEMA.keys())
        for category in CATEGORY_SOURCES:
            if category in defined:
                continue
            self.notebook.add(category)
            tab = self.notebook.tab(category)
            self._build_category_tab(tab, category, {})

    def _build_category_tab(self, tab, category, schema_sections):
        inner = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=6, pady=6)

        if category == "Configuration":
            self._build_noctalia_configuration_info(inner)

        for source_key in CATEGORY_SOURCES.get(category, []):
            src = self.sources[source_key]

            if source_key == "umbriel":
                for sec_name, opts in schema_sections.items():
                    if not opts:
                        continue
                    lf = _labeled_frame(inner, sec_name)
                    for opt in opts:
                        self._create_schema_widget(lf, source_key, opt)

            schema_keys = self._schema_keys_for(source_key, category)
            discovered = {}
            display_cfg = src.merged
            if source_key == "noctalia" and self.noctalia_full_config:
                display_cfg = copy.deepcopy(self.noctalia_full_config)
                deep_merge(display_cfg, src.merged, REPLACE_KEYS)

            if source_key == "noctalia" and category == "Dock":
                enabled = _get_dotted(src.merged, "dock.enabled")
                default_only = enabled is None
                if default_only:
                    enabled = _get_dotted(display_cfg, "dock.enabled")
                if enabled is None:
                    enabled = False
                lf = _labeled_frame(inner, "Dock")
                self._create_discovered_widget(
                    lf, source_key, "dock.enabled", enabled,
                    default_only=default_only, label="Enable Dock (dock.enabled)")

            for key, value in iter_leaf_entries(display_cfg):
                if key in schema_keys:
                    continue
                if (source_key == "noctalia" and category == "Dock"
                        and key == "dock.enabled"):
                    continue
                if (source_key == "noctalia"
                        and (key == "include" or key.startswith("include."))):
                    continue
                if categorize_key(source_key, key) != category:
                    continue
                parent = key.rsplit(".", 1)[0] if "." in key else "(root)"
                is_default = (
                    source_key == "noctalia"
                    and _get_dotted(src.merged, key) is None
                )
                discovered.setdefault(parent, []).append(
                    (key, value, is_default))

            for sec_name, items in discovered.items():
                lf = _labeled_frame(inner, f"{src.name} · {sec_name}")
                for key, value, is_default in items:
                    self._create_discovered_widget(
                        lf, source_key, key, value, default_only=is_default)

    def _build_noctalia_configuration_info(self, parent):
        src = self.sources["noctalia"]
        info = _labeled_frame(parent, "Noctalia configuration files", padding=8)
        lines = [
            f"User TOML files: {NOCTALIA_CONFIG_DIR}",
            f"GUI override file: {src.save_path}",
            "Settings in this tab are read-only file information.",
            "[include] directives must be set in user TOML files; "
            "Noctalia ignores them in settings.toml.",
        ]
        user_files = [
            path for path in src.resolve_load_paths()
            if os.path.dirname(path) == NOCTALIA_CONFIG_DIR
            and os.path.exists(path)
        ]
        if user_files:
            lines.append("Loaded user files:")
            lines.extend(f"  {path}" for path in user_files)
        else:
            lines.append(
                "No user TOML files were found; built-in defaults are shown.")
        if src.save_path in src.per_file:
            lines.append(f"Loaded GUI override: {src.save_path}")
        if self.noctalia_full_config_error:
            lines.append(
                f"Built-in settings could not be loaded: "
                f"{self.noctalia_full_config_error}")
        if self.noctalia_parse_warnings:
            lines.append(
                "Some built-in settings could not be parsed and were skipped:")
            lines.extend(f"  {w}" for w in self.noctalia_parse_warnings[:15])
            if len(self.noctalia_parse_warnings) > 15:
                lines.append(
                    f"  … and {len(self.noctalia_parse_warnings) - 15} more")
        ctk.CTkLabel(info, text="\n".join(lines), justify="left",
                     anchor="w", wraplength=900).pack(fill="x")

    def _schema_keys_for(self, source_key, category):
        if source_key != "umbriel":
            return set()
        result = set()
        sections = UMBRIEL_SCHEMA.get(category, {}) or {}
        for opts in sections.values():
            for opt in opts:
                result.add(opt["key"])
        return result

    def _full_key(self, source_key, config_key):
        return f"{source_key}:{config_key}"

    # ------------------------------------------------------------------
    # Widgets
    # ------------------------------------------------------------------
    def _build_choice_widget(self, row, var, choices, include_current=True):
        """Radio buttons for a few options, a read-only dropdown for many."""
        choices = list(choices)
        cur = var.get()
        if include_current and cur and cur not in choices:
            choices.append(cur)
        if len(choices) <= CHOICE_RADIO_MAX:
            for ch in choices:
                ctk.CTkRadioButton(
                    row, text=ch, variable=var, value=ch).pack(
                        side="left", padx=4)
        else:
            width = min(320, max(120, max(len(c) for c in choices) * 8 + 24))
            ctk.CTkComboBox(
                row, variable=var, values=choices,
                state="readonly", width=width).pack(side="left")

    def _choices_for(self, source_key, key, current):
        """Known options for a string setting, or None for free text."""
        if not isinstance(current, str) or _looks_like_hex_color(current):
            return None
        if source_key == "noctalia" and key == "bar.default.layer":
            return ["top", "overlay"]
        if source_key == "umbriel":
            for rx, ch in self.schema_choice_rules:
                if rx.match(key):
                    return list(ch)
        known = KNOWN_CHOICES.get(key.rsplit(".", 1)[-1])
        if known and current in known:
            return list(known)
        return None

    def _create_schema_widget(self, parent, source_key, opt):
        key = opt["key"]
        label = opt["label"]
        typ = opt["type"]
        default = opt.get("default")
        full = self._full_key(source_key, key)

        current = _get_dotted(self.sources[source_key].merged, key)
        if current is None or (
                source_key == "umbriel"
                and key == "animation.windows_opacity.curve"
                and not str(current).strip()):
            current = default

        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=2)
        ctk.CTkLabel(row, text=label, width=230, anchor="w").pack(side="left")

        choices = opt.get("choices")
        if typ == "text" and isinstance(current, str):
            live = self._choices_for(source_key, key, current)
            if live:
                typ, choices = "choice", live

        if typ == "boolean":
            var = tk.BooleanVar(value=bool(current))
            ctk.CTkCheckBox(row, text="", variable=var).pack(side="left")
            self.vars[full] = var
            self.var_meta[full] = {"kind": "boolean"}

        elif typ == "choice":
            var = tk.StringVar(value=str(current) if current is not None else "")
            self._build_choice_widget(row, var, choices)
            self.vars[full] = var
            self.var_meta[full] = {"kind": "choice"}

        elif typ == "slider":
            var = tk.DoubleVar(value=float(current) if current is not None else 0.0)
            integral_range = (
                isinstance(opt["min"], int) and not isinstance(opt["min"], bool)
                and isinstance(opt["max"], int) and not isinstance(opt["max"], bool)
                and "resolution" not in opt
            )
            number_type = opt.get(
                "number_type", "int" if integral_range else "float")
            step = opt.get("resolution", 1 if number_type == "int" else 0.1)
            NumberInput(
                row, var, opt["min"], opt["max"], step=step,
                length=200).pack(side="left", fill="x", expand=True)
            self.vars[full] = var
            self.var_meta[full] = {
                "kind": "number",
                "number_type": number_type,
            }

        elif typ == "text":
            var = tk.StringVar(value=str(current) if current is not None else "")
            ctk.CTkEntry(row, textvariable=var).pack(
                side="left", fill="x", expand=True)
            self.vars[full] = var
            self.var_meta[full] = {"kind": "text"}

        elif typ == "list":
            list_val = current if isinstance(current, list) else (default or [])
            var = tk.StringVar(value=", ".join(str(x) for x in list_val))
            ctk.CTkEntry(row, textvariable=var).pack(
                side="left", fill="x", expand=True)
            self.vars[full] = var
            self.var_meta[full] = {"kind": "list",
                                   "item_type": opt.get("item_type", "str")}

        elif typ == "color":
            var = tk.StringVar(value=str(current) if current else "#000000FF")
            ctk.CTkEntry(row, textvariable=var, width=120).pack(side="left")
            swatch = ctk.CTkLabel(
                row, text="", width=32, height=28,
                fg_color=_color_preview(var.get()), corner_radius=4)
            swatch.pack(side="left", padx=4)

            def _refresh(*_a, v=var, s=swatch):
                try:
                    s.configure(fg_color=_color_preview(v.get()))
                except tk.TclError:
                    pass
            var.trace_add("write", _refresh)

            def _pick(v=var):
                c = colorchooser.askcolor()[1]
                if c:
                    v.set(c.upper() + "FF")
            ctk.CTkButton(row, text="Pick…", command=_pick).pack(side="left")
            self.vars[full] = var
            self.var_meta[full] = {"kind": "color"}

        elif typ == "raw_aot":
            txt = ctk.CTkTextbox(
                parent, height=160, wrap="none",
                font=ctk.CTkFont(family="TkFixedFont", size=10))
            txt.pack(fill="both", expand=True, pady=(2, 6))
            if isinstance(current, list) and current:
                txt.insert("1.0", serialize_aot(key, current))
            self.raw_widgets[full] = txt
            self.var_meta[full] = {"kind": "aot"}

    def _create_discovered_widget(
            self, parent, source_key, key, value, default_only=False,
            label=None):
        full = self._full_key(source_key, key)
        kind = infer_kind(value)

        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=2)
        ctk.CTkLabel(
            row, text=label or key, width=260, anchor="w").pack(side="left")

        choices = self._choices_for(source_key, key, value) \
            if kind == "text" else None
        is_role = (source_key == "noctalia" and kind == "text"
                   and value in NOCTALIA_COLOR_ROLES)

        if is_role:
            # Noctalia colour settings accept a palette role OR a hex colour.
            var = tk.StringVar(value=value)
            ctk.CTkComboBox(
                row, variable=var, values=NOCTALIA_COLOR_ROLES,
                width=240).pack(side="left")

            def _pick_hex(v=var):
                c = colorchooser.askcolor()[1]
                if c:
                    v.set(c.upper())
            ctk.CTkButton(row, text="Hex…", command=_pick_hex).pack(
                side="left", padx=4)
            ctk.CTkLabel(
                row, text="palette role or #RRGGBB[AA]",
                text_color="#777777").pack(side="left")
            self.vars[full] = var
            self.var_meta[full] = {"kind": "text"}

        elif choices:
            var = tk.StringVar(value=value)
            self._build_choice_widget(
                row, var, choices,
                include_current=not (
                    source_key == "noctalia" and key == "bar.default.layer"))
            self.vars[full] = var
            self.var_meta[full] = {"kind": "choice"}

        elif kind == "boolean":
            var = tk.BooleanVar(value=bool(value))
            ctk.CTkCheckBox(row, text="", variable=var).pack(side="left")
            self.vars[full] = var
            self.var_meta[full] = {"kind": "boolean"}

        elif kind in ("int", "float"):
            var = tk.StringVar(value=str(value))
            ctk.CTkEntry(row, textvariable=var, width=140).pack(side="left")
            self.vars[full] = var
            self.var_meta[full] = {"kind": "number", "number_type": kind}

        elif kind == "color":
            var = tk.StringVar(value=str(value))
            ctk.CTkEntry(row, textvariable=var, width=140).pack(side="left")
            swatch = ctk.CTkLabel(
                row, text="", width=32, height=28,
                fg_color=_color_preview(var.get()), corner_radius=4)
            swatch.pack(side="left", padx=4)

            def _refresh(*_a, v=var, s=swatch):
                try:
                    s.configure(fg_color=_color_preview(v.get()))
                except tk.TclError:
                    pass
            var.trace_add("write", _refresh)

            def _pick(v=var):
                c = colorchooser.askcolor()[1]
                if c:
                    v.set(c.upper() + "FF")
            ctk.CTkButton(row, text="Pick…", command=_pick).pack(side="left")
            self.vars[full] = var
            self.var_meta[full] = {"kind": "color"}

        elif kind == "list":
            item_type = type(value[0]).__name__ if value else "str"
            var = tk.StringVar(value=", ".join(str(x) for x in value))
            ctk.CTkEntry(row, textvariable=var).pack(
                side="left", fill="x", expand=True)
            self.vars[full] = var
            self.var_meta[full] = {"kind": "list", "item_type": item_type}

        elif kind == "aot":
            txt = ctk.CTkTextbox(
                parent, height=120, wrap="none",
                font=ctk.CTkFont(family="TkFixedFont", size=10))
            txt.pack(fill="both", expand=True, pady=(2, 6))
            txt.insert("1.0", serialize_aot(key, value))
            self.raw_widgets[full] = txt
            self.var_meta[full] = {"kind": "aot"}

        else:
            var = tk.StringVar(value=str(value))
            ctk.CTkEntry(row, textvariable=var).pack(
                side="left", fill="x", expand=True)
            self.vars[full] = var
            self.var_meta[full] = {"kind": "text"}

        if default_only:
            self.var_meta[full].update({
                "default_only": True,
                "default_value": value,
            })

    # ------------------------------------------------------------------
    # KeyBinding tab (Umbriel only)
    # ------------------------------------------------------------------
    def _build_keybind_tab(self, frame):
        cols = ("key", "action", "options")
        tree = ttk.Treeview(frame, columns=cols, show="headings", height=18)
        for c, t, w in (("key", "Key", 180),
                        ("action", "Action", 360),
                        ("options", "Options", 260)):
            tree.heading(c, text=t)
            tree.column(c, width=w)
        tree.pack(fill="both", expand=True, padx=5, pady=5)
        self.keybind_tree = tree

        bar = ctk.CTkFrame(frame, fg_color="transparent")
        bar.pack(fill="x", padx=5, pady=5)

        def _add():
            kv, av, ov = (tk.StringVar(value="Mod+X"),
                          tk.StringVar(value="spawn "),
                          tk.StringVar(value=""))
            row = (kv, av, ov)
            self.keybind_rows.append(row)
            iid = tree.insert("", "end", values=(kv.get(), av.get(), ov.get()))
            self.keybind_iids[iid] = row
            self._edit_keybind_row(tree, iid)

        def _edit():
            sel = tree.selection()
            if sel:
                self._edit_keybind_row(tree, sel[0])

        def _remove():
            sel = tree.selection()
            if not sel:
                return
            iid = sel[0]
            row = self.keybind_iids.pop(iid, None)
            tree.delete(iid)
            if row in self.keybind_rows:
                self.keybind_rows.remove(row)

        ctk.CTkButton(bar, text="Add", command=_add).pack(side="left")
        ctk.CTkButton(bar, text="Edit", command=_edit).pack(
            side="left", padx=4)
        ctk.CTkButton(bar, text="Remove", command=_remove).pack(side="left")

        kb = self.sources["umbriel"].merged.get("keybinds")
        if isinstance(kb, dict):
            self._populate_keybinds(kb)
    def _populate_keybinds(self, kb_dict):
        self.keybind_tree.delete(*self.keybind_tree.get_children())
        self.keybind_rows.clear()
        self.keybind_iids.clear()
        for k, v in kb_dict.items():
            kv = tk.StringVar(value=k)
            if isinstance(v, str):
                av = tk.StringVar(value=v)
                ov = tk.StringVar(value="")
            elif isinstance(v, dict):
                av = tk.StringVar(value=str(v.get("action", "")))
                opts = []
                for ok, ov_ in v.items():
                    if ok == "action":
                        continue
                    if isinstance(ov_, bool):
                        opts.append(f"{ok}={'true' if ov_ else 'false'}")
                    elif isinstance(ov_, str):
                        opts.append(f'{ok}="{ov_}"')
                    else:
                        opts.append(f"{ok}={ov_}")
                ov = tk.StringVar(value=", ".join(opts))
            else:
                continue
            row = (kv, av, ov)
            self.keybind_rows.append(row)
            iid = self.keybind_tree.insert(
                "", "end", values=(kv.get(), av.get(), ov.get()))
            self.keybind_iids[iid] = row

    def _edit_keybind_row(self, tree, iid):
        row = self.keybind_iids.get(iid)
        if row is None:
            return
        kv, av, ov = row
        dlg = ctk.CTkToplevel(self.root)
        dlg.title("Edit Keybind")
        dlg.transient(self.root)

        ctk.CTkLabel(dlg, text="Key").grid(
            row=0, column=0, sticky="w", padx=6, pady=4)
        k_e = ctk.CTkEntry(dlg, textvariable=kv, width=300)
        k_e.grid(row=0, column=1, padx=6, pady=4)
        ctk.CTkLabel(dlg, text="Action").grid(
            row=1, column=0, sticky="w", padx=6, pady=4)
        ctk.CTkEntry(dlg, textvariable=av, width=400).grid(
            row=1, column=1, padx=6, pady=4)
        ctk.CTkLabel(dlg, text="Options").grid(
            row=2, column=0, sticky="w", padx=6, pady=4)
        ctk.CTkEntry(dlg, textvariable=ov, width=400).grid(
            row=2, column=1, padx=6, pady=4)

        def _ok():
            tree.item(iid, values=(kv.get(), av.get(), ov.get()))
            dlg.destroy()

        bf = ctk.CTkFrame(dlg, fg_color="transparent")
        bf.grid(row=3, column=0, columnspan=2, pady=8)
        ctk.CTkButton(bf, text="OK", command=_ok).pack(side="left", padx=4)
        ctk.CTkButton(
            bf, text="Cancel", command=dlg.destroy).pack(side="left", padx=4)
        k_e.focus_set()

    # ------------------------------------------------------------------
    # Collecting GUI → config dict (per source)
    # ------------------------------------------------------------------
    def _collect_for_source(self, source_key):
        cfg = {}
        for full, var in self.vars.items():
            src_key, key = full.split(":", 1)
            if src_key != source_key:
                continue
            meta = self.var_meta.get(full, {})
            kind = meta.get("kind")

            try:
                raw = var.get()
            except Exception:
                continue

            if (meta.get("default_only") and kind == "list"
                    and str(raw) == ", ".join(
                        str(x) for x in meta["default_value"])):
                continue

            if (source_key == "umbriel"
                    and key == "animation.windows_opacity.curve"
                    and not str(raw).strip()):
                raw = DEFAULT_ANIMATION_CURVE

            if kind == "list":
                it = meta.get("item_type", "str")
                items = [x.strip() for x in str(raw).split(",") if x.strip()]
                converted = []
                for x in items:
                    try:
                        if it in ("float", "float64"):
                            converted.append(float(x))
                        elif it in ("int", "int64"):
                            converted.append(int(x))
                        else:
                            converted.append(x)
                    except ValueError:
                        converted.append(x)
                value = converted
            elif kind == "number":
                nt = meta.get("number_type", "float")
                try:
                    numeric = float(raw)
                    if nt == "int" and not numeric.is_integer():
                        raise ValueError
                    value = int(numeric) if nt == "int" else numeric
                except (OverflowError, TypeError, ValueError) as exc:
                    expected = "integer" if nt == "int" else "number"
                    raise ValueError(
                        f"{key} must be a valid {expected} value "
                        f"(got {raw!r})") from exc
            elif kind == "boolean":
                value = bool(raw)
            else:
                value = raw

            if meta.get("default_only") and value == meta.get("default_value"):
                continue
            _set_dotted(cfg, key, value)

        for full, widget in self.raw_widgets.items():
            src_key, key = full.split(":", 1)
            if src_key != source_key:
                continue
            text = widget.get("1.0", "end").strip()
            if not text:
                value = []
                if (self.var_meta.get(full, {}).get("default_only")
                        and value == self.var_meta[full].get("default_value")):
                    continue
                _set_dotted(cfg, key, value)
                continue
            try:
                parsed = tomllib.loads(text)
                meta = self.var_meta.get(full, {})
                value = _get_dotted(parsed, key) or []
                if (meta.get("default_only")
                        and value == meta.get("default_value")):
                    continue
                _set_dotted(cfg, key, value)
            except Exception as exc:
                messagebox.showwarning(
                    "Parse Error",
                    f"Could not parse {key} block — using previous value.\n\n{exc}")
                cfg[key] = self.sources[source_key].merged.get(key, [])

        if source_key == "umbriel":
            for key, value in self.dynamic_schema_edits.items():
                _set_dotted(cfg, key, value)

        if source_key == "umbriel" and self.keybind_rows:
            kb = {}
            for kv, av, ov in self.keybind_rows:
                k = kv.get().strip()
                if not k:
                    continue
                action = av.get().strip()
                opts = _parse_kb_options(ov.get())
                if opts:
                    entry = {"action": action}
                    entry.update(opts)
                    kb[k] = entry
                else:
                    kb[k] = action
            cfg["keybinds"] = kb

        return cfg

    # ------------------------------------------------------------------
    # VALIDATE → then save
    # ------------------------------------------------------------------
    def _prepare_and_validate(self, source_key, text):
        """Validate TOML text for ``source_key`` BEFORE writing anything.

        Returns dict:
          ok         – safe to save
          fatal      – True if a hard error (do not save)
          title, body – message to show if not ok
        """
        # 1. Self-parse (catches serialization bugs)
        try:
            tomllib.loads(text)
        except Exception as exc:
            return {"ok": False, "fatal": True,
                    "title": f"{self.sources[source_key].name}: TOML syntax error",
                    "body": f"The generated TOML could not be parsed:\n\n{exc}"}

        # 2. Write temp file for the official validator
        fd, tmp = tempfile.mkstemp(suffix=".toml", prefix=f"{source_key}-")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(text)

            report = run_official_validator(source_key, tmp)

            if not report["installed"]:
                return {"ok": True, "fatal": False,
                        "title": f"{self.sources[source_key].name}: validator not installed",
                        "body": (
                            f"`{source_key} config validate` was not found on PATH,\n"
                            f"so validation was skipped.\n\n"
                            f"The generated TOML parses cleanly via tomllib.\n"
                            f"Install Umbriel/Noctalia to enable full validation.")}

            body = format_diagnostics(report["diagnostics"], report["raw"])

            if not report["ok"]:
                return {"ok": False, "fatal": True,
                        "title": f"{self.sources[source_key].name}: validation FAILED — not saved",
                        "body": body}

            if report["diagnostics"]:
                return {"ok": True, "fatal": False,
                        "title": f"{self.sources[source_key].name}: valid (with warnings)",
                        "body": body + "\n\nThe file will be saved."}

            return {"ok": True, "fatal": False, "title": None, "body": None}
        finally:
            try:
                os.unlink(tmp)
            except OSError:
                pass

    def _prepare_source(self, source_key):
        """Build and validate one source without writing it."""
        src = self.sources[source_key]
        if src.load_errors:
            return {
                "ok": False,
                "fatal": True,
                "title": f"{src.name}: configuration load error",
                "body": "One or more source files could not be parsed. Fix or "
                        "move these files, then Reload before saving:\n\n" +
                        "\n".join(src.load_errors),
            }
        try:
            cfg = self._collect_for_source(source_key)
            remove_keys = [
                full.split(":", 1)[1]
                for full, meta in self.var_meta.items()
                if full.startswith(source_key + ":")
                and meta.get("default_only")
            ]
            text = src.prepare_text(cfg, remove_keys)
        except Exception as exc:
            return {
                "ok": False,
                "fatal": True,
                "title": f"{src.name}: prepare failed",
                "body": f"Could not build config text:\n\n{exc}",
            }

        result = self._prepare_and_validate(source_key, text)
        result["text"] = text
        return result

    def _save_source(self, source_key):
        """Return True on success."""
        src = self.sources[source_key]
        result = self._prepare_source(source_key)

        if result["fatal"]:
            messagebox.showerror(result["title"], result["body"])
            self._set_status(f"{src.name}: ❌ {result['title']}")
            return False

        if result["title"]:                # warning-only path
            messagebox.showwarning(result["title"], result["body"])

        try:
            text = result["text"]
            self._commit(src, text)
            src.merged = tomllib.loads(text)
        except Exception as exc:
            messagebox.showerror(
                f"{src.name}: write failed",
                f"{src.save_path}\n\n{exc}")
            return False

        self._set_status(f"{src.name}: ✓ saved → {src.save_path}")
        return True

    def _commit(self, src, text):
        """Write ``text``; ask before overwriting a real external change."""
        try:
            src.commit(text)
        except ExternalChange:
            if not messagebox.askyesno(
                    f"{src.name}: file changed on disk",
                    f"{src.save_path}\n\nAnother program modified this file "
                    "since it was loaded.\n\nOverwrite it with the values "
                    "from this window? (A .bak copy is kept.)"):
                raise RuntimeError("Save cancelled: file changed on disk.")
            src.loaded_fingerprint = src._fingerprint()
            src.commit(text)

    def _save_all(self):
        prepared = {
            key: self._prepare_source(key)
            for key in self.sources
        }
        failures = [
            f"{result['title']}\n{result['body']}"
            for result in prepared.values() if result["fatal"]
        ]
        if failures:
            messagebox.showerror(
                "Save All: validation failed — nothing saved",
                "\n\n".join(failures))
            self._set_status("Save All aborted; no sources were written.")
            return

        warnings = [
            f"{result['title']}\n{result['body']}"
            for result in prepared.values() if result["title"]
        ]
        if warnings:
            messagebox.showwarning("Save All: validator warnings",
                                   "\n\n".join(warnings))

        for key, result in prepared.items():
            src = self.sources[key]
            try:
                text = result["text"]
                self._commit(src, text)
                src.merged = tomllib.loads(text)
            except Exception as exc:
                messagebox.showerror(
                    f"{src.name}: write failed",
                    f"{src.save_path}\n\n{exc}")
                self._set_status(
                    f"Save All stopped while writing {src.name}; "
                    "validation passed but a write failed.")
                return
        self._set_status("✓ all validated sources saved")

    def _validate_all(self):
        """Validate every source without writing to disk."""
        results = {
            key: self._prepare_source(key)
            for key in self.sources
        }
        failures = [
            f"{result['title']}\n{result['body']}"
            for result in results.values() if result["fatal"]
        ]
        if failures:
            messagebox.showerror("Validation failed", "\n\n".join(failures))
            self._set_status("❌ validation failed; nothing was written")
            return

        warnings = [
            f"{result['title']}\n{result['body']}"
            for result in results.values() if result["title"]
        ]
        if warnings:
            messagebox.showwarning("Validation warnings",
                                   "\n\n".join(warnings))
        self._set_status("✓ validation complete (nothing written)")
        messagebox.showinfo("Validate",
                            "All sources validated successfully.\n"
                            "Nothing was written to disk.")

    # ------------------------------------------------------------------
    def _reload_all(self):
        if self.dynamic_schema_edits and not messagebox.askyesno(
                "Discard pending schema edits?",
                "Reloading will discard pending edits made in the Schema Explorer. Continue?"):
            return
        self.dynamic_schema_edits.clear()
        for src in self.sources.values():
            src.load()
        self._reload_widgets()
        self._set_status("Reloaded from disk")

    def _reload_widgets(self):
        for full, var in self.vars.items():
            src_key, cfg_key = full.split(":", 1)
            value = _get_dotted(self.sources[src_key].merged, cfg_key)
            meta = self.var_meta.get(full, {})
            if value is None and meta.get("default_only"):
                value = meta.get("default_value")
            if value is None:
                continue
            kind = meta.get("kind")
            try:
                if kind == "list":
                    var.set(", ".join(str(x) for x in value))
                elif kind == "boolean":
                    var.set(bool(value))
                else:
                    var.set(value)
            except Exception:
                pass

        for full, widget in self.raw_widgets.items():
            src_key, cfg_key = full.split(":", 1)
            value = _get_dotted(self.sources[src_key].merged, cfg_key)
            meta = self.var_meta.get(full, {})
            if value is None and meta.get("default_only"):
                value = meta.get("default_value")
            widget.delete("1.0", "end")
            if isinstance(value, list) and value:
                widget.insert("1.0", serialize_aot(cfg_key, value))

        if self.keybind_rows:
            kb = self.sources["umbriel"].merged.get("keybinds")
            if isinstance(kb, dict):
                self._populate_keybinds(kb)

    # ------------------------------------------------------------------
    def _set_status(self, text):
        try:
            self.status.configure(text=text)
        except Exception:
            pass


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    ctk.set_appearance_mode("system")
    ctk.set_default_color_theme("blue")
    root = ctk.CTk()
    App(root)
    root.mainloop()