"""Reusable bounded numeric slider: [-] slider [+] [editable value].

Modern edition
--------------
* transparent background, so it sits cleanly on cards
* accent-coloured slider with native step snapping
* editable value box: type a number and press Enter / leave the field
  (values are clamped to the range and snapped to the step; invalid input
  reverts); Up / Down arrows step the value while the box has focus
* round - / + buttons with press-and-hold auto-repeat, dimmed at the limits
* light / dark aware colours (customtkinter (light, dark) tuples)

Public API is unchanged:  NumberInput(master, variable, minimum, maximum,
step=1, length=200)  where ``variable`` is a tk Int/Double/StringVar.
"""

import math
import customtkinter as ctk
import tkinter as tk
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation

# (light, dark) colour pairs - match the main GUI palette.
DEFAULT_ACCENT = ("#3b82f6", "#4c8dff")
DEFAULT_ACCENT_HOVER = ("#2f6fdb", "#3a78e6")
TRACK_COLOR = ("#d7dbe3", "#343744")
BUTTON_COLOR = ("#eef0f5", "#262833")
BUTTON_HOVER = ("#e1e5ee", "#313444")
BORDER_COLOR = ("#e2e5ea", "#2b2d38")
TEXT_COLOR = ("#1f2330", "#e6e8ee")
DISABLED_TEXT = ("#a3a9b8", "#565b6b")

REPEAT_DELAY_MS = 380
REPEAT_INTERVAL_MS = 55
MAX_NATIVE_STEPS = 2000


class NumberInput(ctk.CTkFrame):
    """Slider with decrement/increment buttons and an editable value."""

    def __init__(self, master, variable, minimum, maximum, step=1, length=200,
                 *, accent=DEFAULT_ACCENT, accent_hover=DEFAULT_ACCENT_HOVER):
        super().__init__(master, fg_color="transparent")
        self.variable = variable
        self.minimum = self._finite_number(minimum, "minimum")
        self.maximum = self._finite_number(maximum, "maximum")
        self.step = self._validated_step(step)
        if self.minimum >= self.maximum:
            raise ValueError("minimum must be less than maximum")
        self._syncing = False
        self._editing = False
        self._repeat_job = None
        self._precision = max(
            0, -Decimal(str(self.step)).normalize().as_tuple().exponent)

        self.grid_columnconfigure(1, weight=1)
        self.minus_btn = self._make_step_button("−", -1)
        self.minus_btn.grid(row=0, column=0, padx=(0, 6))

        self.scale = ctk.CTkSlider(
            self, from_=self.minimum, to=self.maximum,
            command=self._on_slider, width=length, height=16,
            number_of_steps=self._native_steps(),
            progress_color=accent, button_color=accent,
            button_hover_color=accent_hover, fg_color=TRACK_COLOR)
        self.scale.grid(row=0, column=1, sticky="ew")

        self.plus_btn = self._make_step_button("+", 1)
        self.plus_btn.grid(row=0, column=2, padx=(6, 8))
        self._text = tk.StringVar()
        self.entry = ctk.CTkEntry(
            self, textvariable=self._text, width=70, height=28,
            corner_radius=8, justify="center", border_color=BORDER_COLOR,
            text_color=TEXT_COLOR)
        self.entry.grid(row=0, column=3)
        bound_font = ctk.CTkFont(size=10)
        self.minimum_label = ctk.CTkLabel(
            self, text=f"min: {self._format_value(self.minimum)}",
            font=bound_font, text_color=DISABLED_TEXT)
        self.minimum_label.grid(
            row=1, column=1, sticky="w", padx=2, pady=(0, 2))
        self.maximum_label = ctk.CTkLabel(
            self, text=f"max: {self._format_value(self.maximum)}",
            font=bound_font, text_color=DISABLED_TEXT)
        self.maximum_label.grid(
            row=1, column=1, sticky="e", padx=2, pady=(0, 2))
        self.entry.bind("<FocusIn>", self._on_entry_focus_in, add="+")
        self.entry.bind("<FocusOut>", self._on_entry_commit, add="+")
        self.entry.bind("<Return>", self._on_entry_commit, add="+")
        self.entry.bind("<KP_Enter>", self._on_entry_commit, add="+")
        self.entry.bind("<Escape>", self._on_entry_cancel, add="+")
        self.entry.bind("<Up>", lambda _e: self._arrow(1), add="+")
        self.entry.bind("<Down>", lambda _e: self._arrow(-1), add="+")

        self._trace_id = variable.trace_add("write", self._update_value)
        try:
            self.scale.set(self._clamp(float(variable.get())))
        except (tk.TclError, TypeError, ValueError):
            self.scale.set(self.minimum)
        self._update_value()

    # ------------------------------------------------------------------
    # Validation helpers (unchanged behaviour)
    # ------------------------------------------------------------------
    @staticmethod
    def _finite_number(value, name):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError(f"{name} must be an int or float")
        result = float(value)
        if not math.isfinite(result):
            raise ValueError(f"{name} must be finite")
        return result

    @classmethod
    def _validated_step(cls, step):
        value = cls._finite_number(step, "step")
        if value <= 0:
            raise ValueError("step must be greater than zero")
        return value

    @staticmethod
    def _stepped_value(value, minimum, maximum, step, direction):
        current = Decimal(str(value))
        delta = Decimal(str(step)) * direction
        low, high = Decimal(str(minimum)), Decimal(str(maximum))
        return float(min(high, max(low, current + delta)))

    def _native_steps(self):
        """Step count for CTkSlider so dragging snaps natively."""
        try:
            span = (Decimal(str(self.maximum)) - Decimal(str(self.minimum))) \
                / Decimal(str(self.step))
        except InvalidOperation:
            return None
        count = int(span.to_integral_value(rounding=ROUND_HALF_UP))
        if count < 1 or count > MAX_NATIVE_STEPS:
            return None
        if abs(span - count) > Decimal("0.000001"):
            return None
        return count

    def _clamp(self, value):
        return min(self.maximum, max(self.minimum, value))

    def _format_value(self, value):
        return f"{value:.{self._precision}f}"

    def _snap(self, value):
        low = Decimal(str(self.minimum))
        step = Decimal(str(self.step))
        count = (
            (Decimal(str(value)) - low) / step
        ).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        snapped = low + count * step
        return float(min(Decimal(str(self.maximum)), max(low, snapped)))

    def _current(self):
        try:
            return float(self.variable.get())
        except (tk.TclError, TypeError, ValueError):
            return None

    # ------------------------------------------------------------------
    # Step buttons (press-and-hold auto repeat)
    # ------------------------------------------------------------------
    def _make_step_button(self, text, direction):
        btn = ctk.CTkButton(
            self, text=text, width=28, height=28, corner_radius=14,
            fg_color=BUTTON_COLOR, hover_color=BUTTON_HOVER,
            text_color=TEXT_COLOR, text_color_disabled=DISABLED_TEXT,
            font=ctk.CTkFont(size=16, weight="bold"))
        btn.bind("<ButtonPress-1>",
                 lambda _e, d=direction: self._start_repeat(d), add="+")
        btn.bind("<ButtonRelease-1>", lambda _e: self._stop_repeat(), add="+")
        btn.bind("<Leave>", lambda _e: self._stop_repeat(), add="+")
        return btn

    def _start_repeat(self, direction):
        self._stop_repeat()
        if not self._step(direction):
            return
        self._repeat_job = self.after(
            REPEAT_DELAY_MS, lambda: self._repeat(direction))

    def _repeat(self, direction):
        self._repeat_job = None
        if self._step(direction):
            self._repeat_job = self.after(
                REPEAT_INTERVAL_MS, lambda: self._repeat(direction))

    def _stop_repeat(self):
        if self._repeat_job is not None:
            try:
                self.after_cancel(self._repeat_job)
            except (tk.TclError, ValueError):
                pass
            self._repeat_job = None

    def _step(self, direction):
        """Step once. Returns True if the value changed."""
        current = self._current()
        if current is None:
            current = self.minimum
        value = self._stepped_value(
            current, self.minimum, self.maximum, self.step, direction)
        if value == current:
            return False
        self.variable.set(value)
        return True

    def _arrow(self, direction):
        self._step(direction)
        return "break"

    # ------------------------------------------------------------------
    # Slider
    # ------------------------------------------------------------------
    def _on_slider(self, value):
        if self._syncing:
            return
        snapped = self._snap(value)
        self._syncing = True
        try:
            self.scale.set(snapped)
            self.variable.set(snapped)
        finally:
            self._syncing = False

    # ------------------------------------------------------------------
    # Editable value box
    # ------------------------------------------------------------------
    def _on_entry_focus_in(self, _event=None):
        self._editing = True

    def _on_entry_cancel(self, _event=None):
        self._editing = False
        self._update_value()
        self.focus_set()
        return "break"

    def _on_entry_commit(self, _event=None):
        text = self._text.get().strip().replace(",", ".")
        self._editing = False
        try:
            typed = float(text)
            if not math.isfinite(typed):
                raise ValueError
        except ValueError:
            self._update_value()          # revert invalid input
            return
        value = self._snap(self._clamp(typed))
        self.variable.set(value)
        self._update_value()              # normalise text even if unchanged
        if _event is not None and getattr(_event, "keysym", "") in (
                "Return", "KP_Enter"):
            self.focus_set()

    # ------------------------------------------------------------------
    # Sync variable -> widgets
    # ------------------------------------------------------------------
    def _update_value(self, *_args):
        value = self._current()
        if value is None:
            if not self._editing:
                self._text.set("")
            return
        if not self._editing:
            self._text.set(self._format_value(value))
        if not self._syncing:
            self._syncing = True
            try:
                self.scale.set(self._clamp(value))
            finally:
                self._syncing = False
        self._update_button_states(value)

    def _update_button_states(self, value):
        eps = 1e-9
        self.minus_btn.configure(
            state="disabled" if value <= self.minimum + eps else "normal")
        self.plus_btn.configure(
            state="disabled" if value >= self.maximum - eps else "normal")

    def destroy(self):
        self._stop_repeat()
        try:
            self.variable.trace_remove("write", self._trace_id)
        except tk.TclError:
            pass
        super().destroy()