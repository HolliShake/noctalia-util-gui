"""Reusable bounded numeric slider with circular step buttons."""

import math
import customtkinter as ctk
import tkinter as tk
from decimal import Decimal, ROUND_HALF_UP


class NumberInput(ctk.CTkFrame):
    """Slider with decrement/increment buttons and a displayed value."""

    def __init__(self, master, variable, minimum, maximum, step=1, length=200):
        super().__init__(master)
        self.variable = variable
        self.minimum = self._finite_number(minimum, "minimum")
        self.maximum = self._finite_number(maximum, "maximum")
        self.step = self._validated_step(step)
        if self.minimum >= self.maximum:
            raise ValueError("minimum must be less than maximum")
        self._syncing = False

        ctk.CTkButton(
            self, text="-", width=28, height=28, corner_radius=14,
            command=lambda: self._step(-1)).pack(side="left", padx=(0, 4))
        self.scale = ctk.CTkSlider(
            self, from_=self.minimum, to=self.maximum,
            command=self._on_slider, width=length)
        self.scale.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(
            self, text="+", width=28, height=28, corner_radius=14,
            command=lambda: self._step(1)).pack(side="left", padx=(4, 6))
        self.value_label = ctk.CTkLabel(self, text="", width=56, anchor="e")
        self.value_label.pack(side="right")

        self._precision = max(
            0, -Decimal(str(self.step)).normalize().as_tuple().exponent)
        self._trace_id = variable.trace_add("write", self._update_value)
        self.scale.set(float(variable.get()))
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

    def _step(self, direction):
        value = self._stepped_value(
            self.variable.get(), self.minimum, self.maximum,
            self.step, direction)
        self.variable.set(value)

    def _snap(self, value):
        low = Decimal(str(self.minimum))
        step = Decimal(str(self.step))
        count = (
            (Decimal(str(value)) - low) / step
        ).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        snapped = low + count * step
        return float(min(Decimal(str(self.maximum)), max(low, snapped)))

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

    def _update_value(self, *_args):
        try:
            value = float(self.variable.get())
        except (tk.TclError, TypeError, ValueError):
            self.value_label.configure(text="")
            return
        self.value_label.configure(text=f"{value:.{self._precision}f}")
        if not self._syncing:
            self._syncing = True
            try:
                self.scale.set(value)
            finally:
                self._syncing = False

    def destroy(self):
        try:
            self.variable.trace_remove("write", self._trace_id)
        except tk.TclError:
            pass
        super().destroy()