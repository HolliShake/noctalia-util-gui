#!/usr/bin/env python3
"""CustomTkinter interface for Noctalia and Umbriel configuration.

UI highlights
-------------
  * Sidebar navigation, card-style collapsible sections, toggle switches,
    segmented controls
  * Global search (Ctrl+F) across every category, with per-category match counts
  * Unsaved-changes indicator, Ctrl+S to save, toast notifications
  * Light / Dark / System appearance (including the tree views)
  * Pages are built in the background so the window opens instantly

Configuration loading and persistence live in :mod:`config`.
"""

import customtkinter as ctk
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk, colorchooser, messagebox, simpledialog
import config
from number_input import NumberInput

# ---------------------------------------------------------------------------
# Visual theme
# ---------------------------------------------------------------------------
# All colours are (light, dark) tuples understood by customtkinter.
ACCENT = ("#3b82f6", "#4c8dff")
ACCENT_HOVER = ("#2f6fdb", "#3a78e6")
ACCENT_SOFT = ("#e3ecff", "#26304d")
COL_BG = ("#f3f4f7", "#14151a")
COL_SIDEBAR = ("#ffffff", "#191a20")
COL_CARD = ("#ffffff", "#1e2028")
COL_BORDER = ("#e2e5ea", "#2b2d38")
COL_HOVER = ("#eef0f5", "#262833")
COL_TEXT = ("#1f2330", "#e6e8ee")
COL_MUTED = ("#6b7280", "#8b90a0")
COL_WARN = ("#b45309", "#f5b041")
COL_DANGER = ("#dc2626", "#ef4444")
COL_DANGER_HOVER = ("#fee2e2", "#3a1d1f")

TOAST_COLORS = {
    "success": ("#16a34a", "#16a34a"),
    "error": ("#dc2626", "#dc2626"),
    "warn": ("#d97706", "#d97706"),
    "info": ("#3b82f6", "#3b82f6"),
}
TOAST_ICONS = {"success": "✓", "error": "✕", "warn": "!", "info": "i"}

NAV_LABELS = {
    "Compositor (Umbriel)": "Compositor",
}

_HEADING_FONT = None   # keep a reference so Tk does not delete the named font

def _is_dark():
    return ctk.get_appearance_mode() == "Dark"

def tree_palette():
    if _is_dark():
        return dict(bg="#1e2028", alt="#232530", fg="#e6e8ee", head="#262833",
                    head_fg="#c5c9d6", sel="#3b4a8a", border="#2b2d38",
                    trough="#1a1b22", unknown="#e0a060")
    return dict(bg="#ffffff", alt="#f6f7fa", fg="#1f2330", head="#eef0f5",
                head_fg="#454b5e", sel="#5b7cff", border="#e2e5ea",
                trough="#f3f4f7", unknown="#b06020")

def apply_ttk_theme():
    """Style ttk widgets (Treeview, Scrollbar) to match the CTk appearance."""
    global _HEADING_FONT
    p = tree_palette()
    style = ttk.Style()
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    _HEADING_FONT = tkfont.nametofont("TkDefaultFont").copy()
    _HEADING_FONT.configure(weight="bold")
    style.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
    style.configure(
        "Treeview", background=p["bg"], fieldbackground=p["bg"],
        foreground=p["fg"], borderwidth=0, relief="flat", rowheight=32)
    style.configure(
        "Treeview.Heading", background=p["head"], foreground=p["head_fg"],
        relief="flat", borderwidth=0, padding=(10, 7), font=_HEADING_FONT)
    style.map("Treeview",
              background=[("selected", p["sel"])],
              foreground=[("selected", "#ffffff")])
    style.map("Treeview.Heading", background=[("active", p["head"])])
    for orient in ("Vertical", "Horizontal"):
        style.configure(
            f"{orient}.TScrollbar", background=p["head"],
            troughcolor=p["trough"], bordercolor=p["trough"],
            lightcolor=p["head"], darkcolor=p["head"],
            arrowcolor=p["head_fg"], relief="flat", gripcount=0)
        style.map(f"{orient}.TScrollbar",
                  background=[("active", p["border"])])

def style_tree(tree):
    p = tree_palette()
    tree.tag_configure("even", background=p["bg"])
    tree.tag_configure("odd", background=p["alt"])
    tree.tag_configure("unknown", foreground=p["unknown"])

def restripe(tree):
    for i, iid in enumerate(tree.get_children("")):
        tags = [t for t in tree.item(iid, "tags") if t not in ("odd", "even")]
        tags.append("odd" if i % 2 else "even")
        tree.item(iid, tags=tuple(tags))

def _tokens_match(text, tokens):
    return all(t in text for t in tokens)

def _prettify(key):
    leaf = key.rsplit(".", 1)[-1].replace("_", " ").replace("-", " ").strip()
    return leaf[:1].upper() + leaf[1:] if leaf else key

def _color_preview(hex_rgba):
    try:
        h = hex_rgba.lstrip("#")
        return "#" + (h[:6] if len(h) == 8 else h)
    except Exception:
        return "#000000"

CHOICE_RADIO_MAX = 5  # compact choices render as segmented controls

# ---------------------------------------------------------------------------
# Small UI helpers
# ---------------------------------------------------------------------------
def primary_button(parent, text, command, width=110, height=34):
    return ctk.CTkButton(
        parent, text=text, command=command, width=width, height=height,
        corner_radius=8, fg_color=ACCENT, hover_color=ACCENT_HOVER,
        text_color="#ffffff", font=ctk.CTkFont(size=13, weight="bold"))

def ghost_button(parent, text, command, width=90, height=34, danger=False):
    return ctk.CTkButton(
        parent, text=text, command=command, width=width, height=height,
        corner_radius=8, fg_color="transparent", border_width=1,
        border_color=COL_DANGER if danger else COL_BORDER,
        text_color=COL_DANGER if danger else COL_TEXT,
        hover_color=COL_DANGER_HOVER if danger else COL_HOVER,
        font=ctk.CTkFont(size=13))

# ---------------------------------------------------------------------------
# Main app
# ---------------------------------------------------------------------------
class App:
    BASE_TITLE = "Noctalia + Umbriel Configuration"

    def __init__(self, root):
        self.root = root
        self.root.title(self.BASE_TITLE)
        self.root.geometry("1220x820")
        self.root.minsize(980, 620)
        try:
            self.root.configure(fg_color=COL_BG)
        except Exception:
            pass

        self.config = config.ConfigManager()

        self.vars = {}
        self.var_meta = {}
        self.raw_widgets = {}
        self.keybind_rows = []
        self.keybind_iids = {}
        self.keybind_tree = None
        self.kb_count = None
        self._keybinds_touched = False

        self.pages = {}
        self.page_order = []
        self.current_page = None
        self.query = ""
        self._search_job = None
        self._bg_job = None
        self.dirty = False
        self._suspend_dirty = False
        self._toast_label = None
        self._toast_job = None
        self._styled_trees = []
        self._explorer = None

        self._build_layout()
        self._build_pages()

        self.root.bind("<Control-s>", lambda _e: self._save_all())
        self.root.bind("<Control-f>", lambda _e: self._focus_search())
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self._set_status(self._describe_loaded_short())

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------
    def _build_layout(self):
        root = self.root
        root.grid_columnconfigure(1, weight=1)
        root.grid_rowconfigure(0, weight=1)

        # ---- Sidebar -------------------------------------------------
        self.sidebar = ctk.CTkFrame(
            root, width=236, corner_radius=0, fg_color=COL_SIDEBAR)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.pack_propagate(False)

        brand = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        brand.pack(fill="x", padx=20, pady=(22, 14))
        ctk.CTkLabel(
            brand, text="Settings", anchor="w", text_color=COL_TEXT,
            font=ctk.CTkFont(size=22, weight="bold")).pack(fill="x")
        ctk.CTkLabel(
            brand, text="Noctalia  ·  Umbriel", anchor="w",
            text_color=COL_MUTED, font=ctk.CTkFont(size=12)).pack(fill="x")

        self.nav_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        self.nav_frame.pack(fill="both", expand=True)

        foot = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        foot.pack(fill="x", side="bottom", padx=12, pady=(6, 16))
        ctk.CTkButton(
            foot, text="Schema Explorer", anchor="w", height=34,
            corner_radius=8, fg_color="transparent", hover_color=COL_HOVER,
            text_color=COL_TEXT, font=ctk.CTkFont(size=13),
            command=self._open_schema_explorer).pack(fill="x", pady=1)
        ctk.CTkButton(
            foot, text="Config sources", anchor="w", height=34,
            corner_radius=8, fg_color="transparent", hover_color=COL_HOVER,
            text_color=COL_TEXT, font=ctk.CTkFont(size=13),
            command=self._show_sources_info).pack(fill="x", pady=1)
        ctk.CTkLabel(
            foot, text="Appearance", anchor="w", text_color=COL_MUTED,
            font=ctk.CTkFont(size=11)).pack(fill="x", padx=6, pady=(10, 2))
        self.theme_switch = ctk.CTkSegmentedButton(
            foot, values=["System", "Light", "Dark"],
            command=self._on_theme, selected_color=ACCENT,
            selected_hover_color=ACCENT_HOVER, height=28)
        self.theme_switch.set("System")
        self.theme_switch.pack(fill="x", padx=2)

        # ---- Main area -----------------------------------------------
        self.main = ctk.CTkFrame(root, fg_color="transparent")
        self.main.grid(row=0, column=1, sticky="nsew")
        self.main.grid_columnconfigure(0, weight=1)
        self.main.grid_rowconfigure(2, weight=1)

        header = ctk.CTkFrame(self.main, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=24, pady=(20, 8))
        header.grid_columnconfigure(0, weight=1)

        titles = ctk.CTkFrame(header, fg_color="transparent")
        titles.grid(row=0, column=0, sticky="w")
        self.title_label = ctk.CTkLabel(
            titles, text="", anchor="w", text_color=COL_TEXT,
            font=ctk.CTkFont(size=24, weight="bold"))
        self.title_label.pack(fill="x")
        self.subtitle_label = ctk.CTkLabel(
            titles, text="", anchor="w", text_color=COL_MUTED,
            font=ctk.CTkFont(size=12))
        self.subtitle_label.pack(fill="x")

        actions = ctk.CTkFrame(header, fg_color="transparent")
        actions.grid(row=0, column=1, sticky="e")
        self.dirty_label = ctk.CTkLabel(
            actions, text="●  Unsaved changes", text_color=COL_WARN,
            font=ctk.CTkFont(size=12, weight="bold"))
        self.dirty_label.grid(row=0, column=0, padx=(0, 14))
        self.dirty_label.grid_remove()
        ghost_button(actions, "Reload", self._reload_all, width=80).grid(
            row=0, column=1, padx=3)
        ghost_button(actions, "Validate", self._validate_all, width=84).grid(
            row=0, column=2, padx=3)
        primary_button(actions, "Save All", self._save_all, width=100).grid(
            row=0, column=3, padx=(3, 0))

        search_wrap = ctk.CTkFrame(self.main, fg_color="transparent")
        search_wrap.grid(row=1, column=0, sticky="ew", padx=24, pady=(0, 10))
        self.search_entry = ctk.CTkEntry(
            search_wrap, height=38, corner_radius=10, fg_color=COL_CARD,
            border_color=COL_BORDER, text_color=COL_TEXT,
            placeholder_text="Search settings across all categories…   (Ctrl+F · Esc to clear)")
        self.search_entry.pack(fill="x")
        self.search_entry.bind("<KeyRelease>", self._on_search_key)

        self.content = ctk.CTkFrame(self.main, fg_color="transparent")
        self.content.grid(row=2, column=0, sticky="nsew", padx=(16, 12))

        statusbar = ctk.CTkFrame(
            self.main, height=30, corner_radius=0, fg_color=COL_SIDEBAR)
        statusbar.grid(row=3, column=0, sticky="ew")
        self.status = ctk.CTkLabel(
            statusbar, anchor="w", text_color=COL_MUTED,
            font=ctk.CTkFont(size=12))
        self.status.pack(side="left", padx=16, pady=4)
        ctk.CTkLabel(
            statusbar, text="Ctrl+S  save all", text_color=COL_MUTED,
            font=ctk.CTkFont(size=11)).pack(side="right", padx=16)

    # ------------------------------------------------------------------
    # Status / toast / dirty helpers
    # ------------------------------------------------------------------
    def _set_status(self, text):
        try:
            self.status.configure(text=text)
        except Exception:
            pass

    def _busy(self, text):
        self._set_status(text)
        try:
            self.root.configure(cursor="watch")
            self.root.update_idletasks()
        except tk.TclError:
            pass

    def _idle(self):
        try:
            self.root.configure(cursor="")
        except tk.TclError:
            pass

    def _toast(self, text, kind="info", ms=3200):
        color = TOAST_COLORS.get(kind, TOAST_COLORS["info"])
        icon = TOAST_ICONS.get(kind, "i")
        if self._toast_label is None:
            self._toast_label = ctk.CTkLabel(
                self.root, text="", height=42, corner_radius=10,
                text_color="#ffffff", font=ctk.CTkFont(size=13, weight="bold"))
        self._toast_label.configure(text=f"   {icon}   {text}   ", fg_color=color)
        self._toast_label.place(relx=1.0, rely=1.0, x=-24, y=-52, anchor="se")
        self._toast_label.lift()
        if self._toast_job is not None:
            try:
                self.root.after_cancel(self._toast_job)
            except Exception:
                pass
        self._toast_job = self.root.after(ms, self._hide_toast)

    def _hide_toast(self):
        self._toast_job = None
        if self._toast_label is not None:
            self._toast_label.place_forget()

    def _mark_dirty(self):
        if self.dirty:
            return
        self.dirty = True
        self.dirty_label.grid()
        self.root.title("● " + self.BASE_TITLE)

    def _mark_clean(self):
        self.dirty = False
        self.dirty_label.grid_remove()
        self.root.title(self.BASE_TITLE)

    def _on_var_write(self, *_a):
        if not self._suspend_dirty:
            self._mark_dirty()

    def _track(self, var):
        var.trace_add("write", self._on_var_write)

    def _register(self, full, var, meta):
        self.vars[full] = var
        self.var_meta[full] = meta
        self._track(var)

    def _on_close(self):
        if self.dirty and not messagebox.askyesno(
                "Unsaved changes",
                "You have unsaved changes. Quit without saving?"):
            return
        self.root.destroy()

    def _on_theme(self, value):
        ctk.set_appearance_mode(value.lower())
        self.root.after(120, self._restyle_trees)

    def _restyle_trees(self):
        apply_ttk_theme()
        alive = []
        for t in self._styled_trees:
            try:
                if t.winfo_exists():
                    style_tree(t)
                    alive.append(t)
            except tk.TclError:
                pass
        self._styled_trees = alive

    def _register_tree(self, tree):
        style_tree(tree)
        self._styled_trees.append(tree)

    def _focus_search(self):
        self.search_entry.focus_set()
        return "break"

    # ------------------------------------------------------------------
    # Info text
    # ------------------------------------------------------------------
    def _describe_loaded_short(self):
        bits = []
        for s in self.config.sources.values():
            label = f"{s.name}: {len(s.per_file)} file(s)"
            if s.load_errors:
                label += f" ⚠ {len(s.load_errors)} error(s)"
            bits.append(label)
        if self.config.noctalia_full_config_error:
            bits.append("Noctalia defaults unavailable")
        return "   ·   ".join(bits)

    def _describe_loaded(self):
        lines = []
        for s in self.config.sources.values():
            lines.append(f"{s.name}")
            lines.append(f"  writes to: {s.save_path}")
            lines.append(f"  loaded files: {len(s.per_file)}")
            for p in s.per_file:
                lines.append(f"    • {p}")
            for e in s.load_errors:
                lines.append(f"    ⚠ {e}")
            lines.append("")
        if self.config.noctalia_full_config_error:
            lines.append("Noctalia built-in settings could not be loaded:")
            lines.append(f"  {self.config.noctalia_full_config_error}")
        return "\n".join(lines).strip()

    def _show_sources_info(self):
        messagebox.showinfo("Config sources", self._describe_loaded())

    # ------------------------------------------------------------------
    # Pages / navigation
    # ------------------------------------------------------------------
    def _build_pages(self):
        for category in config.CATEGORY_SOURCES:
            self._add_page(category)
        self._show_page(self.page_order[0])
        self._schedule_background_build()

    def _add_page(self, name):
        btn = ctk.CTkButton(
            self.nav_frame, text=NAV_LABELS.get(name, name), anchor="w",
            height=38, corner_radius=8, fg_color="transparent",
            hover_color=COL_HOVER, text_color=COL_TEXT,
            font=ctk.CTkFont(size=13),
            command=lambda n=name: self._show_page(n))
        btn.pack(fill="x", padx=12, pady=2)
        self.pages[name] = {
            "name": name, "nav": btn, "built": False, "frame": None,
            "body": None, "sections": [], "empty": None, "stale": False,
        }
        self.page_order.append(name)

    def _build_page(self, name):
        page = self.pages[name]
        if page["built"]:
            return
        page["built"] = True
        if name == "KeyBinding":
            frame = ctk.CTkFrame(self.content, fg_color="transparent")
            page["frame"] = frame
            self._build_keybind_tab(page)
            return
        frame = ctk.CTkScrollableFrame(self.content, fg_color="transparent")
        page["frame"] = frame
        page["body"] = frame
        page["empty"] = ctk.CTkLabel(
            frame, text="", text_color=COL_MUTED, font=ctk.CTkFont(size=14))
        self._build_category_tab(
            page, name, config.UMBRIEL_SCHEMA.get(name) or {})
        if not page["sections"] and not page.get("pinned"):
            page["empty"].configure(
                text="No settings were found for this category.")
            page["empty"].pack(pady=60)

    def _show_page(self, name):
        old = self.current_page
        if old is not None and old != name:
            frame = self.pages[old]["frame"]
            if frame is not None:
                frame.pack_forget()
        self._build_page(name)
        page = self.pages[name]
        self.current_page = name
        if page["stale"]:
            self._repack_page(name)
        page["frame"].pack(fill="both", expand=True)
        self.title_label.configure(text=NAV_LABELS.get(name, name))
        names = " · ".join(
            self.config.sources[k].name
            for k in config.CATEGORY_SOURCES.get(name, []))
        self.subtitle_label.configure(text=f"Applies to: {names}")
        self._refresh_nav()

    def _refresh_nav(self):
        tokens = self._tokens()
        for name in self.page_order:
            page = self.pages[name]
            active = name == self.current_page
            label = NAV_LABELS.get(name, name)
            muted = False
            if tokens:
                count = self._page_match_count(name, tokens)
                if count:
                    label = f"{label}   ·   {count}"
                else:
                    muted = True
            page["nav"].configure(
                text=label,
                fg_color=ACCENT_SOFT if active else "transparent",
                text_color=ACCENT if active else (
                    COL_MUTED if muted else COL_TEXT))

    def _schedule_background_build(self):
        pending = [n for n in self.page_order if not self.pages[n]["built"]]
        if not pending:
            return
        self._bg_job = self.root.after(60, self._background_step)

    def _background_step(self):
        self._bg_job = None
        try:
            for n in self.page_order:
                if not self.pages[n]["built"]:
                    self._build_page(n)
                    break
        except tk.TclError:
            return
        self._schedule_background_build()

    def _ensure_all_built(self):
        pending = [n for n in self.page_order if not self.pages[n]["built"]]
        if not pending:
            return
        self._busy("Preparing all settings…")
        for n in pending:
            self._build_page(n)
        self._idle()
        self._set_status(self._describe_loaded_short())

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------
    def _tokens(self):
        return self.query.split()

    def _kb_match(self, iid, tokens):
        row = self.keybind_iids.get(iid)
        if row is None:
            return False
        text = " ".join(v.get() for v in row).lower()
        return _tokens_match(text, tokens)

    def _page_match_count(self, name, tokens):
        page = self.pages[name]
        if not page["built"]:
            return 0
        if name == "KeyBinding":
            return sum(1 for iid in self.keybind_iids
                       if self._kb_match(iid, tokens))
        return sum(1 for s in page["sections"] for r in s["rows"]
                   if _tokens_match(r["text"], tokens))

    def _on_search_key(self, event=None):
        if event is not None and event.keysym == "Escape":
            self.search_entry.delete(0, "end")
        if self._search_job is not None:
            try:
                self.root.after_cancel(self._search_job)
            except Exception:
                pass
        self._search_job = self.root.after(140, self._run_search)

    def _run_search(self):
        self._search_job = None
        q = self.search_entry.get().strip().lower()
        if q == self.query:
            return
        self.query = q
        tokens = self._tokens()
        if tokens:
            self._ensure_all_built()
        for p in self.pages.values():
            p["stale"] = True
        target = self.current_page
        if tokens and self._page_match_count(target, tokens) == 0:
            for n in self.page_order:
                if self._page_match_count(n, tokens) > 0:
                    target = n
                    break
        self._show_page(target)

    def _repack_page(self, name):
        page = self.pages[name]
        page["stale"] = False
        tokens = self._tokens()
        if name == "KeyBinding":
            self._filter_keybinds(tokens)
            return
        if not page["built"]:
            return
        for sec in page["sections"]:
            sec["card"].pack_forget()
            sec["content"].pack_forget()
            for r in sec["rows"]:
                r["frame"].pack_forget()
        page["empty"].pack_forget()
        total = 0
        for sec in page["sections"]:
            visible = [r for r in sec["rows"]
                       if not tokens or _tokens_match(r["text"], tokens)]
            if not visible:
                continue
            sec["card"].pack(fill="x", padx=4, pady=6)
            if not sec["collapsed"] or tokens:
                sec["content"].pack(fill="x", padx=14, pady=(0, 10))
            for r in visible:
                r["frame"].pack(fill="x")
            total += len(visible)
        if total == 0 and page["sections"]:
            page["empty"].configure(
                text=f"No settings match “{self.query}”.")
            page["empty"].pack(pady=60)

    # ------------------------------------------------------------------
    # Cards / rows
    # ------------------------------------------------------------------
    def _new_section(self, page, title):
        card = ctk.CTkFrame(
            page["body"], corner_radius=12, fg_color=COL_CARD,
            border_width=1, border_color=COL_BORDER)
        card.pack(fill="x", padx=4, pady=6)
        sec = {"title": title, "card": card, "rows": [], "collapsed": False}
        header = ctk.CTkButton(
            card, text=f"▾   {title}", anchor="w", height=38,
            corner_radius=10, fg_color="transparent", hover_color=COL_HOVER,
            text_color=COL_TEXT, font=ctk.CTkFont(size=14, weight="bold"),
            command=lambda s=sec: self._toggle_section(s))
        header.pack(fill="x", padx=6, pady=(6, 0))
        content = ctk.CTkFrame(card, fg_color="transparent")
        content.pack(fill="x", padx=14, pady=(0, 10))
        sec["header"] = header
        sec["content"] = content
        page["sections"].append(sec)
        return sec

    def _toggle_section(self, sec):
        sec["collapsed"] = not sec["collapsed"]
        arrow = "▸" if sec["collapsed"] else "▾"
        sec["header"].configure(text=f"{arrow}   {sec['title']}")
        if sec["collapsed"] and not self._tokens():
            sec["content"].pack_forget()
        else:
            sec["content"].pack(fill="x", padx=14, pady=(0, 10))

    def _new_row(self, sec, title, subtitle=None, wide=False):
        """Create a settings row. Returns (row_frame, control_container)."""
        row = ctk.CTkFrame(sec["content"], fg_color="transparent")
        row.pack(fill="x")
        row.grid_columnconfigure(0, minsize=280)
        row.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            row, text=title, anchor="w", justify="left", wraplength=270,
            text_color=COL_TEXT, font=ctk.CTkFont(size=13)).grid(
                row=0, column=0, sticky="sw", padx=(2, 0),
                pady=(8, 0 if subtitle else 8))
        if subtitle:
            ctk.CTkLabel(
                row, text=subtitle, anchor="w", justify="left",
                wraplength=270, text_color=COL_MUTED,
                font=ctk.CTkFont(size=11)).grid(
                    row=1, column=0, sticky="nw", padx=(2, 0), pady=(0, 8))
        ctrl = ctk.CTkFrame(row, fg_color="transparent")
        if wide:
            ctrl.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        else:
            ctrl.grid(row=0, column=1, rowspan=2, sticky="ew",
                      padx=(12, 2), pady=6)
        sec["rows"].append({
            "frame": row,
            "text": f"{title} {subtitle or ''} {sec['title']}".lower(),
        })
        return row, ctrl

    # ------------------------------------------------------------------
    # Category tab
    # ------------------------------------------------------------------
    def _build_category_tab(self, page, category, schema_sections):
        if category == "Configuration":
            self._build_noctalia_configuration_info(page)

        for source_key in config.CATEGORY_SOURCES.get(category, []):
            if source_key == "umbriel":
                for sec_name, opts in schema_sections.items():
                    if not opts:
                        continue
                    sec = self._new_section(page, sec_name)
                    for opt in opts:
                        self._create_schema_widget(sec, source_key, opt)

            for section_name, items in self.config.category_sections(
                    source_key, category):
                sec = self._new_section(page, section_name)
                for key, value, is_default in items:
                    label = "Enable dock" if key == "dock.enabled" \
                        and section_name == "Dock" else None
                    self._create_discovered_widget(
                        sec, source_key, key, value,
                        default_only=is_default, label=label)

    def _build_noctalia_configuration_info(self, page):
        src = self.config.sources["noctalia"]
        page["pinned"] = True
        card = ctk.CTkFrame(
            page["body"], corner_radius=12, fg_color=COL_CARD,
            border_width=1, border_color=COL_BORDER)
        card.pack(fill="x", padx=4, pady=6)
        ctk.CTkLabel(
            card, text="Noctalia configuration files", anchor="w",
            text_color=COL_TEXT, font=ctk.CTkFont(size=14, weight="bold")).pack(
                fill="x", padx=18, pady=(14, 4))
        lines = [
            f"User TOML files: {config.NOCTALIA_CONFIG_DIR}",
            f"GUI override file: {src.save_path}",
            "Settings in this tab are read-only file information.",
            "[include] directives must be set in user TOML files; "
            "Noctalia ignores them in settings.toml.",
        ]
        user_files = self.config.noctalia_user_files()
        if user_files:
            lines.append("Loaded user files:")
            lines.extend(f"  {path}" for path in user_files)
        else:
            lines.append(
                "No user TOML files were found; built-in defaults are shown.")
        if src.save_path in src.per_file:
            lines.append(f"Loaded GUI override: {src.save_path}")
        if self.config.noctalia_full_config_error:
            lines.append(
                f"Built-in settings could not be loaded: "
                f"{self.config.noctalia_full_config_error}")
        if self.config.noctalia_parse_warnings:
            lines.append(
                "Some built-in settings could not be parsed and were skipped:")
            lines.extend(
                f"  {w}" for w in self.config.noctalia_parse_warnings[:15])
            if len(self.config.noctalia_parse_warnings) > 15:
                lines.append(
                    f"  … and {len(self.config.noctalia_parse_warnings) - 15} "
                    "more")
        ctk.CTkLabel(
            card, text="\n".join(lines), justify="left", anchor="w",
            wraplength=820, text_color=COL_MUTED,
            font=ctk.CTkFont(size=12)).pack(fill="x", padx=18, pady=(0, 14))

    def _full_key(self, source_key, config_key):
        return f"{source_key}:{config_key}"

    # ------------------------------------------------------------------
    # Widgets
    # ------------------------------------------------------------------
    def _build_choice_widget(
            self, ctrl, var, choices, include_current=True,
            force_dropdown=False):
        """Segmented control for a few short options, dropdown otherwise."""
        choices = list(choices)
        cur = var.get()
        if include_current and cur and cur not in choices:
            choices.append(cur)
        compact = (not force_dropdown
                   and len(choices) <= CHOICE_RADIO_MAX
                   and sum(len(c) for c in choices) <= 44)
        if compact:
            seg = ctk.CTkSegmentedButton(
                ctrl, values=choices, variable=var, height=30,
                selected_color=ACCENT, selected_hover_color=ACCENT_HOVER)
            seg.pack(side="left")
        else:
            width = min(320, max(140, max(len(c) for c in choices) * 8 + 40))
            ctk.CTkComboBox(
                ctrl, variable=var, values=choices, state="readonly",
                width=width, height=32, corner_radius=8,
                button_color=ACCENT, button_hover_color=ACCENT_HOVER).pack(
                    side="left")

    def _switch(self, ctrl, var):
        sw = ctk.CTkSwitch(
            ctrl, text="", variable=var, width=46, switch_width=40,
            switch_height=20, progress_color=ACCENT)
        sw.pack(side="left")
        return sw

    def _color_controls(self, ctrl, var, entry_width):
        ctk.CTkEntry(
            ctrl, textvariable=var, width=entry_width, height=32,
            corner_radius=8).pack(side="left")
        swatch = ctk.CTkLabel(
            ctrl, text="", width=34, height=30,
            fg_color=_color_preview(var.get()), corner_radius=8)
        swatch.pack(side="left", padx=8)

        def _refresh(*_a, v=var, s=swatch):
            try:
                s.configure(fg_color=_color_preview(v.get()))
            except Exception:
                pass
        var.trace_add("write", _refresh)

        def _pick(v=var):
            c = colorchooser.askcolor()[1]
            if c:
                v.set(c.upper() + "FF")
        ghost_button(ctrl, "Pick…", _pick, width=70, height=30).pack(
            side="left")

    def _bind_text_dirty(self, txt):
        def _on_key(e):
            if e.char or e.keysym in ("BackSpace", "Delete", "Return"):
                self._mark_dirty()
        txt.bind("<KeyRelease>", _on_key)
        txt.bind("<<Paste>>", lambda _e: self._mark_dirty())
        txt.bind("<<Cut>>", lambda _e: self._mark_dirty())

    def _create_schema_widget(self, sec, source_key, opt):
        key = opt["key"]
        label = opt["label"]
        typ = opt["type"]
        default = opt.get("default")
        full = self._full_key(source_key, key)

        current = self.config.get_value(source_key, key)
        if current is None or (
                source_key == "umbriel"
                and key == "animation.windows_opacity.curve"
                and not str(current).strip()):
            current = default

        _row, ctrl = self._new_row(
            sec, label, key, wide=(typ == "raw_aot"))

        choices = opt.get("choices")
        if typ == "text" and isinstance(current, str):
            live = self.config.choices_for(source_key, key, current)
            if live:
                typ, choices = "choice", live

        if typ == "boolean":
            var = tk.BooleanVar(value=bool(current))
            self._switch(ctrl, var)
            self._register(full, var, {"kind": "boolean"})

        elif typ == "choice":
            var = tk.StringVar(value=str(current) if current is not None else "")
            self._build_choice_widget(ctrl, var, choices)
            self._register(full, var, {"kind": "choice"})

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
                ctrl, var, opt["min"], opt["max"], step=step,
                length=200).pack(side="left", fill="x", expand=True)
            self._register(full, var, {
                "kind": "number",
                "number_type": number_type,
            })

        elif typ == "text":
            var = tk.StringVar(value=str(current) if current is not None else "")
            ctk.CTkEntry(
                ctrl, textvariable=var, height=32, corner_radius=8).pack(
                    side="left", fill="x", expand=True)
            self._register(full, var, {"kind": "text"})

        elif typ == "list":
            list_val = current if isinstance(current, list) else (default or [])
            var = tk.StringVar(value=", ".join(str(x) for x in list_val))
            ctk.CTkEntry(
                ctrl, textvariable=var, height=32, corner_radius=8,
                placeholder_text="comma, separated, values").pack(
                    side="left", fill="x", expand=True)
            self._register(full, var, {
                "kind": "list", "item_type": opt.get("item_type", "str")})

        elif typ == "color":
            var = tk.StringVar(value=str(current) if current else "#000000FF")
            self._color_controls(ctrl, var, 130)
            self._register(full, var, {"kind": "color"})

        elif typ == "raw_aot":
            txt = ctk.CTkTextbox(
                ctrl, height=170, wrap="none", corner_radius=8,
                border_width=1, border_color=COL_BORDER,
                font=ctk.CTkFont(family="TkFixedFont", size=11))
            txt.pack(fill="both", expand=True)
            if isinstance(current, list) and current:
                txt.insert("1.0", config.serialize_aot(key, current))
            self._bind_text_dirty(txt)
            self.raw_widgets[full] = txt
            self.var_meta[full] = {"kind": "aot"}

    def _create_discovered_widget(
            self, sec, source_key, key, value, default_only=False,
            label=None):
        full = self._full_key(source_key, key)
        kind = config.infer_kind(value)

        _row, ctrl = self._new_row(
            sec, label or _prettify(key), key, wide=(kind == "aot"))

        choices = self.config.choices_for(source_key, key, value) \
            if kind == "text" else None
        is_role = (source_key == "noctalia" and kind == "text"
                   and value in config.NOCTALIA_COLOR_ROLES)

        meta = None
        if is_role:
            # Noctalia colour settings accept a palette role OR a hex colour.
            var = tk.StringVar(value=value)
            ctk.CTkComboBox(
                ctrl, variable=var, values=config.NOCTALIA_COLOR_ROLES, width=240,
                height=32, corner_radius=8, button_color=ACCENT,
                button_hover_color=ACCENT_HOVER).pack(side="left")

            def _pick_hex(v=var):
                c = colorchooser.askcolor()[1]
                if c:
                    v.set(c.upper())
            ghost_button(ctrl, "Hex…", _pick_hex, width=64, height=30).pack(
                side="left", padx=8)
            ctk.CTkLabel(
                ctrl, text="palette role or #RRGGBB[AA]",
                text_color=COL_MUTED, font=ctk.CTkFont(size=11)).pack(
                    side="left")
            meta = {"kind": "text"}
            self._register(full, var, meta)

        elif choices:
            var = tk.StringVar(value=value)
            self._build_choice_widget(
                ctrl, var, choices,
                include_current=not (
                    source_key == "noctalia"
                    and key in config.NOCTALIA_RESTRICTED_LAYER_KEYS),
                force_dropdown=(
                    source_key == "noctalia"
                    and key in config.NOCTALIA_THEME_CHOICE_KEYS))
            meta = {"kind": "choice"}
            self._register(full, var, meta)

        elif kind == "boolean":
            var = tk.BooleanVar(value=bool(value))
            self._switch(ctrl, var)
            meta = {"kind": "boolean"}
            self._register(full, var, meta)

        elif kind in ("int", "float") and config.is_opacity_value(key):
            var = tk.DoubleVar(value=float(value))
            NumberInput(
                ctrl, var, 0.1, 1.0, step=0.1, length=200).pack(
                    side="left", fill="x", expand=True)
            meta = {"kind": "number", "number_type": "float"}
            self._register(full, var, meta)

        elif kind in ("int", "float"):
            var = tk.StringVar(value=str(value))
            ctk.CTkEntry(
                ctrl, textvariable=var, width=150, height=32,
                corner_radius=8).pack(side="left")
            meta = {"kind": "number", "number_type": kind}
            self._register(full, var, meta)

        elif kind == "color":
            var = tk.StringVar(value=str(value))
            self._color_controls(ctrl, var, 140)
            meta = {"kind": "color"}
            self._register(full, var, meta)

        elif kind == "list":
            item_type = type(value[0]).__name__ if value else "str"
            var = tk.StringVar(value=", ".join(str(x) for x in value))
            ctk.CTkEntry(
                ctrl, textvariable=var, height=32, corner_radius=8).pack(
                    side="left", fill="x", expand=True)
            meta = {"kind": "list", "item_type": item_type}
            self._register(full, var, meta)

        elif kind == "aot":
            txt = ctk.CTkTextbox(
                ctrl, height=130, wrap="none", corner_radius=8,
                border_width=1, border_color=COL_BORDER,
                font=ctk.CTkFont(family="TkFixedFont", size=11))
            txt.pack(fill="both", expand=True)
            txt.insert("1.0", config.serialize_aot(key, value))
            self._bind_text_dirty(txt)
            self.raw_widgets[full] = txt
            meta = {"kind": "aot"}
            self.var_meta[full] = meta

        else:
            var = tk.StringVar(value=str(value))
            ctk.CTkEntry(
                ctrl, textvariable=var, height=32, corner_radius=8).pack(
                    side="left", fill="x", expand=True)
            meta = {"kind": "text"}
            self._register(full, var, meta)

        if default_only and meta is not None:
            meta.update({
                "default_only": True,
                "default_value": value,
            })

    # ------------------------------------------------------------------
    # KeyBinding tab (Umbriel only)
    # ------------------------------------------------------------------
    def _build_keybind_tab(self, page):
        frame = page["frame"]

        bar = ctk.CTkFrame(frame, fg_color="transparent")
        bar.pack(fill="x", padx=4, pady=(2, 8))
        self.kb_count = ctk.CTkLabel(
            bar, text="", text_color=COL_MUTED, font=ctk.CTkFont(size=12))
        self.kb_count.pack(side="left", padx=2)
        ghost_button(bar, "Remove", self._remove_keybind, width=84,
                     danger=True).pack(side="right", padx=(4, 0))
        ghost_button(bar, "Edit", lambda: self._edit_selected_keybind(),
                     width=70).pack(side="right", padx=4)
        primary_button(bar, "+  Add keybind", lambda: self._edit_keybind_row(),
                       width=130).pack(side="right", padx=4)

        card = ctk.CTkFrame(
            frame, corner_radius=12, fg_color=COL_CARD,
            border_width=1, border_color=COL_BORDER)
        card.pack(fill="both", expand=True, padx=4, pady=4)
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(0, weight=1)

        cols = ("key", "action", "options")
        tree = ttk.Treeview(
            card, columns=cols, show="headings", selectmode="browse")
        for c, t, w, stretch in (("key", "Key", 200, False),
                                 ("action", "Action", 380, True),
                                 ("options", "Options", 260, True)):
            tree.heading(c, text=t, anchor="w")
            tree.column(c, width=w, anchor="w", stretch=stretch)
        sb = ttk.Scrollbar(card, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        tree.grid(row=0, column=0, sticky="nsew", padx=(8, 0), pady=8)
        sb.grid(row=0, column=1, sticky="ns", padx=(0, 8), pady=8)
        self._register_tree(tree)
        self.keybind_tree = tree

        tree.bind("<Double-1>", self._on_kb_double_click)
        tree.bind("<Return>", lambda _e: self._edit_selected_keybind())
        tree.bind("<Delete>", lambda _e: self._remove_keybind())

        ctk.CTkLabel(
            frame,
            text="Double-click or press Enter to edit  ·  Delete to remove  ·  "
                 "the search box filters this list",
            text_color=COL_MUTED, font=ctk.CTkFont(size=11), anchor="w").pack(
                fill="x", padx=6, pady=(2, 4))

        kb = self.config.sources["umbriel"].merged.get("keybinds")
        if isinstance(kb, dict):
            self._populate_keybinds(kb)
        self._update_keybind_count()

    def _update_keybind_count(self):
        if self.kb_count is None:
            return
        total = len(self.keybind_iids)
        shown = len(self.keybind_tree.get_children("")) \
            if self.keybind_tree is not None else total
        text = f"{total} keybind{'s' if total != 1 else ''}"
        if shown != total:
            text += f"  ·  {shown} shown"
        self.kb_count.configure(text=text)

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
        restripe(self.keybind_tree)
        self._update_keybind_count()

    def _filter_keybinds(self, tokens):
        tree = self.keybind_tree
        if tree is None:
            return
        for iid in self.keybind_iids:
            tree.detach(iid)
        for iid in self.keybind_iids:
            if not tokens or self._kb_match(iid, tokens):
                tree.move(iid, "", "end")
        restripe(tree)
        self._update_keybind_count()

    def _on_kb_double_click(self, event):
        iid = self.keybind_tree.identify_row(event.y)
        if iid:
            self._edit_keybind_row(iid)

    def _edit_selected_keybind(self):
        sel = self.keybind_tree.selection()
        if sel:
            self._edit_keybind_row(sel[0])

    def _remove_keybind(self):
        tree = self.keybind_tree
        sel = tree.selection()
        if not sel:
            return
        iid = sel[0]
        row = self.keybind_iids.pop(iid, None)
        tree.delete(iid)
        if row in self.keybind_rows:
            self.keybind_rows.remove(row)
        self._keybinds_touched = True
        self._mark_dirty()
        restripe(tree)
        self._update_keybind_count()

    def _edit_keybind_row(self, iid=None):
        """Add (iid=None) or edit a keybind in a modal dialog."""
        tree = self.keybind_tree
        existing = self.keybind_iids.get(iid) if iid else None
        if iid and existing is None:
            return
        if existing:
            init = (existing[0].get(), existing[1].get(), existing[2].get())
        else:
            init = ("Mod+X", "spawn ", "")

        dlg = ctk.CTkToplevel(self.root, fg_color=COL_BG)
        dlg.title("Edit keybind" if existing else "Add keybind")
        dlg.transient(self.root)
        dlg.resizable(False, False)

        body = ctk.CTkFrame(
            dlg, corner_radius=12, fg_color=COL_CARD, border_width=1,
            border_color=COL_BORDER)
        body.pack(fill="both", expand=True, padx=16, pady=16)
        body.grid_columnconfigure(0, weight=1)

        kv = tk.StringVar(value=init[0])
        av = tk.StringVar(value=init[1])
        ov = tk.StringVar(value=init[2])

        def field(r, title, hint, var):
            ctk.CTkLabel(
                body, text=title, anchor="w", text_color=COL_TEXT,
                font=ctk.CTkFont(size=13, weight="bold")).grid(
                    row=r * 3, column=0, sticky="w", padx=18,
                    pady=(14 if r == 0 else 8, 0))
            e = ctk.CTkEntry(
                body, textvariable=var, width=440, height=34,
                corner_radius=8)
            e.grid(row=r * 3 + 1, column=0, padx=18, pady=(4, 0), sticky="ew")
            ctk.CTkLabel(
                body, text=hint, anchor="w", text_color=COL_MUTED,
                font=ctk.CTkFont(size=11)).grid(
                    row=r * 3 + 2, column=0, sticky="w", padx=18)
            return e

        k_e = field(0, "Key", "e.g.  Mod+Return,  Mod+Shift+Q", kv)
        a_e = field(1, "Action", "e.g.  spawn kitty,  close-window", av)
        o_e = field(2, "Options",
                    "optional, comma separated:  repeat=true, label=\"Term\"", ov)

        err = ctk.CTkLabel(
            body, text="", anchor="w", text_color=COL_DANGER,
            font=ctk.CTkFont(size=12))
        err.grid(row=9, column=0, sticky="w", padx=18, pady=(8, 0))

        def _ok(_e=None):
            k = kv.get().strip()
            a = av.get().strip()
            o = ov.get().strip()
            if not k:
                err.configure(text="Key is required.")
                return
            if not a:
                err.configure(text="Action is required.")
                return
            for other, r in self.keybind_iids.items():
                if other != iid and r[0].get().strip() == k:
                    err.configure(text=f"'{k}' is already bound.")
                    return
            for part in o.split(","):
                part = part.strip()
                if part and "=" not in part:
                    err.configure(
                        text=f"Option '{part}' must look like name=value.")
                    return
            vals = (k, a, o)
            if existing:
                existing[0].set(k)
                existing[1].set(a)
                existing[2].set(o)
                tree.item(iid, values=vals)
                target = iid
            else:
                row = (tk.StringVar(value=k), tk.StringVar(value=a),
                       tk.StringVar(value=o))
                self.keybind_rows.append(row)
                target = tree.insert("", "end", values=vals)
                self.keybind_iids[target] = row
            self._keybinds_touched = True
            self._mark_dirty()
            dlg.destroy()
            self._filter_keybinds(self._tokens())
            if target in tree.get_children(""):
                tree.selection_set(target)
                tree.see(target)

        btns = ctk.CTkFrame(body, fg_color="transparent")
        btns.grid(row=10, column=0, sticky="e", padx=18, pady=(10, 16))
        ghost_button(btns, "Cancel", dlg.destroy, width=80).pack(
            side="left", padx=4)
        primary_button(
            btns, "Save" if existing else "Add", _ok, width=90).pack(
                side="left", padx=4)

        dlg.bind("<Return>", _ok)
        dlg.bind("<Escape>", lambda _e: dlg.destroy())
        k_e.focus_set()
        try:
            dlg.wait_visibility()
            dlg.grab_set()
        except tk.TclError:
            pass

    # ------------------------------------------------------------------
    # Schema explorer
    # ------------------------------------------------------------------
    def _open_schema_explorer(self):
        if self._explorer is not None:
            try:
                if self._explorer.winfo_exists():
                    self._explorer.lift()
                    self._explorer.focus_force()
                    return
            except tk.TclError:
                pass

        win = ctk.CTkToplevel(self.root, fg_color=COL_BG)
        self._explorer = win
        win.title("Umbriel Configuration Schema Explorer")
        win.geometry("1120x740")
        win.minsize(820, 520)
        win.after(150, win.lift)

        top = ctk.CTkFrame(win, fg_color="transparent")
        top.pack(fill="x", padx=20, pady=(18, 8))
        titles = ctk.CTkFrame(top, fg_color="transparent")
        titles.pack(side="left")
        ctk.CTkLabel(
            titles, text="Schema Explorer", anchor="w", text_color=COL_TEXT,
            font=ctk.CTkFont(size=22, weight="bold")).pack(fill="x")
        ctk.CTkLabel(
            titles,
            text="Live schema from the installed Umbriel binary "
                 "(umbriel config schema --json)",
            anchor="w", text_color=COL_MUTED,
            font=ctk.CTkFont(size=12)).pack(fill="x")

        filter_row = ctk.CTkFrame(win, fg_color="transparent")
        filter_row.pack(fill="x", padx=20, pady=(0, 8))
        filter_entry = ctk.CTkEntry(
            filter_row, height=36, corner_radius=10, fg_color=COL_CARD,
            border_color=COL_BORDER,
            placeholder_text="Filter by key, type or description…")
        filter_entry.pack(side="left", fill="x", expand=True)
        count_label = ctk.CTkLabel(
            filter_row, text="", text_color=COL_MUTED,
            font=ctk.CTkFont(size=12))
        count_label.pack(side="left", padx=(12, 0))

        status = ctk.CTkLabel(
            win, text="Loading schema…", anchor="w", text_color=COL_MUTED,
            font=ctk.CTkFont(size=12))
        status.pack(fill="x", padx=22, pady=(0, 4))

        card = ctk.CTkFrame(
            win, corner_radius=12, fg_color=COL_CARD, border_width=1,
            border_color=COL_BORDER)
        card.pack(fill="both", expand=True, padx=20, pady=4)
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(0, weight=1)

        columns = ("type", "default", "range", "values", "status")
        tree = ttk.Treeview(card, columns=columns, show="tree headings")
        tree.heading("#0", text="Configuration key", anchor="w")
        tree.column("#0", width=350)
        for col, title, width in (
            ("type", "Type", 100), ("default", "Default", 140),
            ("range", "Range", 130), ("values", "Accepted values", 220),
            ("status", "Current config", 120)
        ):
            tree.heading(col, text=title, anchor="w")
            tree.column(col, width=width, anchor="w")
        ysb = ttk.Scrollbar(card, orient="vertical", command=tree.yview)
        xsb = ttk.Scrollbar(card, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=ysb.set, xscrollcommand=xsb.set)
        tree.grid(row=0, column=0, sticky="nsew", padx=(8, 0), pady=(8, 0))
        ysb.grid(row=0, column=1, sticky="ns", padx=(0, 8), pady=(8, 0))
        xsb.grid(row=1, column=0, sticky="ew", padx=(8, 0), pady=(0, 8))
        self._register_tree(tree)

        details = ctk.CTkTextbox(
            win, height=130, wrap="word", state="disabled", corner_radius=10,
            border_width=1, border_color=COL_BORDER, fg_color=COL_CARD,
            font=ctk.CTkFont(family="TkFixedFont", size=11))
        details.pack(fill="x", padx=20, pady=(8, 18))

        rows_by_iid = {}
        state = {"rows": [], "entries": [], "meta": ""}

        def show_details(_event=None):
            selection = tree.selection()
            if not selection:
                return
            row = rows_by_iid.get(selection[0], {})
            lines = [
                f"Key:             {row.get('path', '')}",
                f"Type:            {row.get('type', 'unknown')}",
                f"Default:         {row.get('default', '')}",
                f"Range:           {row.get('range', '')}",
                f"Accepted values: {row.get('values', '')}",
                f"Format:          {row.get('format', '')}",
            ]
            if row.get("description"):
                lines.append(f"Description:     {row['description']}")
            if row.get("deprecated"):
                lines.append("WARNING: This key is marked deprecated by the schema.")
            details.configure(state="normal")
            details.delete("1.0", "end")
            details.insert("1.0", "\n".join(lines))
            details.configure(state="disabled")
        tree.bind("<<TreeviewSelect>>", show_details)

        def build_entries():
            state["entries"] = self.config.schema_explorer_entries(
                state["rows"])

        def render(_event=None):
            tokens = filter_entry.get().strip().lower().split()
            tree.delete(*tree.get_children())
            rows_by_iid.clear()
            shown = 0
            for row, values, extra in state["entries"]:
                hay = " ".join([
                    row["path"], str(row.get("type", "")),
                    str(row.get("description", ""))]).lower()
                if tokens and not _tokens_match(hay, tokens):
                    continue
                stripe = "odd" if shown % 2 else "even"
                iid = tree.insert(
                    "", "end", text=row["path"], values=values,
                    tags=(stripe,) + tuple(extra))
                rows_by_iid[iid] = row
                shown += 1
            count_label.configure(
                text=f"{shown} of {len(state['entries'])} keys")
        filter_entry.bind("<KeyRelease>", render)

        def refresh():
            status.configure(text="Querying installed Umbriel schema…")
            win.update_idletasks()
            try:
                payload, rows = self.config.fetch_schema()
                if not rows:
                    raise RuntimeError(
                        "Schema JSON was valid, but no key entries with a `path` "
                        "field were found. The installed CLI may use a different schema format."
                    )
                state["rows"] = rows
                version = payload.get("version", "unknown") if isinstance(payload, dict) else "unknown"
                revision = payload.get("revision", "unknown") if isinstance(payload, dict) else "unknown"
                state["meta"] = (f"{len(rows)} schema keys · Umbriel {version} · "
                                 f"revision {revision}")
                build_entries()
                render()
                status.configure(text=state["meta"], text_color=COL_MUTED)
            except Exception as exc:
                status.configure(text=f"Schema unavailable: {exc}",
                                 text_color=COL_DANGER)
                messagebox.showerror("Schema Explorer", str(exc), parent=win)

        def edit_selected(_event=None):
            selection = tree.selection()
            if not selection:
                messagebox.showinfo("Schema Explorer", "Select a schema key first.", parent=win)
                return
            row = rows_by_iid.get(selection[0])
            if not row or row.get("unsupported"):
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
            current = self.config.dynamic_schema_edits.get(
                key, self.config.get_value("umbriel", key))
            if current is None:
                current = row.get("default")
            initial = config.toml_value(current) if current is not None else ""
            literal = simpledialog.askstring(
                "Set Umbriel value",
                f"Enter a TOML value for {key} (e.g. true, 42, \"text\", [\"a\", \"b\"]):",
                initialvalue=initial, parent=win)
            if literal is None:
                return
            try:
                parsed = config.parse_toml_value(literal)
            except Exception as exc:
                messagebox.showerror("Invalid TOML value", str(exc), parent=win)
                return
            self.config.dynamic_schema_edits[key] = parsed
            self._mark_dirty()
            build_entries()
            render()
            status.configure(
                text=f"Pending edit: {key} = {config.toml_value(parsed)}. "
                     "Save All to write it.", text_color=COL_WARN)
            self._toast(f"Pending edit: {key}", "info")

        tree.bind("<Double-1>", edit_selected)
        ghost_button(top, "Refresh", refresh, width=90).pack(
            side="right", padx=4)
        primary_button(
            top, "Edit selected key…", edit_selected, width=160).pack(
                side="right", padx=4)
        refresh()

    def _config_form_state(self):
        variables = {}
        for full, variable in self.vars.items():
            try:
                variables[full] = variable.get()
            except Exception:
                continue
        raw_blocks = {
            full: widget.get("1.0", "end").strip()
            for full, widget in self.raw_widgets.items()
        }
        keybind_rows = [
            (key.get(), action.get(), options.get())
            for key, action, options in self.keybind_rows
        ]
        return {
            "variables": variables,
            "raw_blocks": raw_blocks,
            "metadata": self.var_meta,
            "dynamic_schema_edits": self.config.dynamic_schema_edits,
            "keybind_rows": keybind_rows,
            "keybinds_touched": self._keybinds_touched,
        }

    def _confirm_overwrite(self, source):
        return messagebox.askyesno(
            f"{source.name}: file changed on disk",
            f"{source.save_path}\n\nAnother program modified this file "
            "since it was loaded.\n\nOverwrite it with the values "
            "from this window? (A .bak copy is kept.)")

    def _save_source(self, source_key):
        """Return True on success."""
        self._ensure_all_built()
        src = self.config.sources[source_key]
        self._busy(f"Validating {src.name}…")
        result = self.config.prepare_source(
            source_key, self._config_form_state())
        self._idle()
        for warning in result.get("warnings", []):
            messagebox.showwarning("Parse Error", warning)

        if result["fatal"]:
            messagebox.showerror(result["title"], result["body"])
            self._set_status(f"{src.name}: ❌ {result['title']}")
            self._toast(f"{src.name}: validation failed", "error")
            return False

        if result["title"]:                # warning-only path
            messagebox.showwarning(result["title"], result["body"])

        try:
            text = result["text"]
            self.config.commit(source_key, text, self._confirm_overwrite)
        except Exception as exc:
            messagebox.showerror(
                f"{src.name}: write failed",
                f"{src.save_path}\n\n{exc}")
            return False

        if source_key == "umbriel":
            self.config.dynamic_schema_edits.clear()
        self._set_status(f"{src.name}: ✓ saved → {src.save_path}")
        self._toast(f"{src.name} saved", "success")
        return True

    def _save_all(self):
        self._ensure_all_built()
        self._busy("Validating…")
        prepared = self.config.prepare_all(self._config_form_state())
        self._idle()
        collection_warnings = [
            warning
            for result in prepared.values()
            for warning in result.get("warnings", [])
        ]
        if collection_warnings:
            messagebox.showwarning(
                "Parse Error", "\n\n".join(collection_warnings))
        failures = [
            f"{result['title']}\n{result['body']}"
            for result in prepared.values() if result["fatal"]
        ]
        if failures:
            messagebox.showerror(
                "Save All: validation failed — nothing saved",
                "\n\n".join(failures))
            self._set_status("Save All aborted; no sources were written.")
            self._toast("Validation failed — nothing saved", "error")
            return

        warnings = [
            f"{result['title']}\n{result['body']}"
            for result in prepared.values() if result["title"]
        ]
        if warnings:
            messagebox.showwarning("Save All: validator warnings",
                                   "\n\n".join(warnings))

        for key, result in prepared.items():
            src = self.config.sources[key]
            try:
                text = result["text"]
                self.config.commit(key, text, self._confirm_overwrite)
            except Exception as exc:
                messagebox.showerror(
                    f"{src.name}: write failed",
                    f"{src.save_path}\n\n{exc}")
                self._set_status(
                    f"Save All stopped while writing {src.name}; "
                    "validation passed but a write failed.")
                self._toast(f"Write failed: {src.name}", "error")
                return
        self.config.dynamic_schema_edits.clear()
        self._mark_clean()
        self._set_status("✓ all validated sources saved")
        self._toast("All changes saved", "success")

    def _validate_all(self):
        """Validate every source without writing to disk."""
        self._ensure_all_built()
        self._busy("Validating…")
        results = self.config.prepare_all(self._config_form_state())
        self._idle()
        collection_warnings = [
            warning
            for result in results.values()
            for warning in result.get("warnings", [])
        ]
        if collection_warnings:
            messagebox.showwarning(
                "Parse Error", "\n\n".join(collection_warnings))
        failures = [
            f"{result['title']}\n{result['body']}"
            for result in results.values() if result["fatal"]
        ]
        if failures:
            messagebox.showerror("Validation failed", "\n\n".join(failures))
            self._set_status("❌ validation failed; nothing was written")
            self._toast("Validation failed", "error")
            return

        warnings = [
            f"{result['title']}\n{result['body']}"
            for result in results.values() if result["title"]
        ]
        if warnings:
            messagebox.showwarning("Validation warnings",
                                   "\n\n".join(warnings))
            self._toast("Valid, with warnings", "warn")
        else:
            self._toast("All sources valid — nothing written", "success")
        self._set_status("✓ validation complete (nothing written)")

    # ------------------------------------------------------------------
    def _reload_all(self):
        if self.dirty and not messagebox.askyesno(
                "Discard unsaved changes?",
                "Reloading will discard all unsaved changes, including pending "
                "Schema Explorer edits. Continue?"):
            return
        self.config.dynamic_schema_edits.clear()
        self._keybinds_touched = False
        self.config.reload_sources()
        self._reload_widgets()
        self._mark_clean()
        self._set_status("Reloaded from disk")
        self._toast("Reloaded from disk", "info")

    def _reload_widgets(self):
        self._suspend_dirty = True
        try:
            for full, var in self.vars.items():
                src_key, cfg_key = full.split(":", 1)
                value = self.config.get_value(src_key, cfg_key)
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
                value = self.config.get_value(src_key, cfg_key)
                meta = self.var_meta.get(full, {})
                if value is None and meta.get("default_only"):
                    value = meta.get("default_value")
                widget.delete("1.0", "end")
                if isinstance(value, list) and value:
                    widget.insert(
                        "1.0", config.serialize_aot(cfg_key, value))

            if self.keybind_tree is not None:
                kb = self.config.sources["umbriel"].merged.get("keybinds")
                self._populate_keybinds(kb if isinstance(kb, dict) else {})
                self._filter_keybinds(self._tokens())
        finally:
            self._suspend_dirty = False

# ---------------------------------------------------------------------------
if __name__ == "__main__":
    ctk.set_appearance_mode("system")
    ctk.set_default_color_theme("blue")
    root = ctk.CTk()
    apply_ttk_theme()
    App(root)
    root.mainloop()