"""Reusable bounded numeric slider with circular step buttons."""

import math
import tkinter as tk
from decimal import Decimal
from tkinter import ttk


class NumberInput(ttk.Frame):
    """Slider with decrement/increment buttons and a displayed value."""

    def __init__(self, master, variable, minimum, maximum, step=1, length=200):
        super().__init__(master)
        self.variable = variable
        self.minimum = self._finite_number(minimum, "minimum")
        self.maximum = self._finite_number(maximum, "maximum")
        self.step = self._validated_step(step)
        if self.minimum >= self.maximum:
            raise ValueError("minimum must be less than maximum")

        style = ttk.Style(self)
        background = style.lookup("TFrame", "background") or "#f0f0f0"
        foreground = style.lookup("TLabel", "foreground") or "#333333"
        self._make_circle_button("-", -1, background, foreground).pack(
            side="left", padx=(0, 4))

        self.scale = tk.Scale(
            self, variable=variable, from_=self.minimum, to=self.maximum,
            resolution=self.step, orient="horizontal", showvalue=False,
            length=length, highlightthickness=0, bd=0)
        self.scale.pack(side="left", fill="x", expand=True)

        self._make_circle_button("+", 1, background, foreground).pack(
            side="left", padx=(4, 6))
        self.value_text = tk.StringVar(self)
        ttk.Label(self, textvariable=self.value_text, width=8,
                  anchor="e").pack(side="right")

        self._precision = max(
            0, -Decimal(str(self.step)).normalize().as_tuple().exponent)
        self._trace_id = variable.trace_add("write", self._update_value)
        self._update_value()

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

    def _make_circle_button(self, label, direction, background, foreground):
        button = tk.Canvas(
            self, width=24, height=24, highlightthickness=0, bd=0,
            background=background, cursor="hand2", takefocus=True)
        button.create_oval(
            2, 2, 22, 22, outline=foreground, fill=background, width=1)
        button.create_text(
            12, 12, text=label, fill=foreground,
            font=("TkDefaultFont", 10, "bold"))
        button.bind(
            "<Button-1>",
            lambda _event: self._step(direction))
        button.bind(
            "<KeyPress-space>",
            lambda _event: self._step(direction))
        button.bind(
            "<KeyPress-Return>",
            lambda _event: self._step(direction))
        return button

    def _step(self, direction):
        value = self._stepped_value(
            self.variable.get(), self.minimum, self.maximum,
            self.step, direction)
        self.scale.set(value)

    def _update_value(self, *_args):
        try:
            value = float(self.variable.get())
        except (tk.TclError, TypeError, ValueError):
            self.value_text.set("")
            return
        self.value_text.set(f"{value:.{self._precision}f}")

    def destroy(self):
        try:
            self.variable.trace_remove("write", self._trace_id)
        except tk.TclError:
            pass
        super().destroy()