"""The data viewer: eight EEG channels, ten seconds, sweeping left to
right with a cursor at the newest sample, as in Unicorn Recorder, drawn
the way g.Pype's TimeSeriesScope draws: light traces on the window colour,
a faint grid, channel names on the left axis.

To the right of the traces, a column shows each channel's signal quality
on that channel's row."""
from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QVBoxLayout, QWidget

from .. import layout, quality
from . import theme

QUALITY_COLOURS = {quality.GOOD: theme.GOOD, quality.BAD: theme.BAD,
                   quality.UNKNOWN: theme.UNKNOWN}
QUALITY_TEXT = {quality.GOOD: "good", quality.BAD: "bad",
                quality.UNKNOWN: "settling"}
#: Height of both bottom axes, so the two plots' rows line up.
BOTTOM_AXIS_HEIGHT = 40


class _TimeAxis(pg.AxisItem):
    """Labels each second of the sweep with the time of the sample now
    shown there, so the labels wrap where the cursor is."""

    def __init__(self):
        super().__init__("bottom")
        self.window = 10.0
        self.cursor = 0.0
        self.sweep_start = 0.0

    def tickStrings(self, values, scale, spacing):
        labels = []
        for x in values:
            t = self.sweep_start + x
            if x > self.cursor:
                t -= self.window
            labels.append(f"{t:.0f}" if t >= 0 else "")
        return labels


class Scope(QWidget):
    """Shows the EEG columns of a SweepTap's buffer."""

    def __init__(self, seconds: float = 10.0, parent=None):
        super().__init__(parent)
        self.seconds = seconds
        self.fs = layout.SAMPLING_RATE
        self.scale_uv = 50.0
        self.channels = layout.NUM_EEG

        self.axis = _TimeAxis()
        self.axis.window = seconds
        self.plot = pg.GraphicsLayoutWidget()
        self.plot.setBackground(theme.WINDOW)
        self.plot.ci.layout.setHorizontalSpacing(0)
        item = self.plot.addPlot(row=0, col=0,
                                 axisItems={"bottom": self.axis})
        self.plot_item = item
        item.setMenuEnabled(False)
        item.hideButtons()
        item.setMouseEnabled(False, False)
        item.vb.setDefaultPadding(0)
        item.setXRange(0, seconds, padding=0)
        item.setYRange(0, self.channels, padding=0)
        item.showGrid(x=True, y=False, alpha=0.3)
        muted = pg.mkPen(theme.MUTED)
        for name in ("left", "bottom"):
            axis = item.getAxis(name)
            axis.setPen(muted)
            axis.setTextPen(pg.mkPen(theme.TEXT))
        self.axis.setTickSpacing(major=1.0, minor=1.0)
        item.getAxis("left").setTicks([[
            (self.channels - i - 0.5, f"CH{i + 1}")
            for i in range(self.channels)]])
        item.getAxis("left").setWidth(48)
        self.axis.setHeight(BOTTOM_AXIS_HEIGHT)
        item.setLabel("bottom", "Time (s)", color=theme.MUTED)
        self._set_left_label()

        # Row separators, fainter than the grid, as in g.Pype's scope.
        separator = pg.mkPen(255, 255, 255, 40)
        for row in range(1, self.channels):
            item.addItem(pg.InfiniteLine(row, angle=0, pen=separator))

        self.x = np.arange(int(seconds * self.fs)) / self.fs
        trace = pg.mkPen(theme.TEXT, width=1)
        self.curves = []
        for _ in range(self.channels):
            curve = pg.PlotDataItem(pen=trace, connect="finite",
                                    skipFiniteCheck=False)
            item.addItem(curve)
            self.curves.append(curve)
        self.triggers = pg.PlotDataItem(
            pen=pg.mkPen(theme.TRIGGER, width=1, style=Qt.PenStyle.DashLine),
            connect="finite")
        item.addItem(self.triggers)
        self.cursor = pg.InfiniteLine(0, angle=90,
                                      pen=pg.mkPen(theme.CURSOR, width=2))
        self.cursor.hide()
        item.addItem(self.cursor)

        self._quality_column(item)

        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.addWidget(self.plot)

    def _quality_column(self, scope) -> None:
        """A narrow plot beside the traces, its rows linked to theirs,
        with one quality indicator per channel."""
        item = self.plot.addPlot(row=0, col=1)
        item.setMenuEnabled(False)
        item.hideButtons()
        item.setMouseEnabled(False, False)
        item.hideAxis("left")
        item.setYLink(scope)
        item.setXRange(0, 1, padding=0)
        item.setFixedWidth(64)
        bottom = item.getAxis("bottom")
        bottom.setHeight(BOTTOM_AXIS_HEIGHT)
        bottom.setTicks([[]])
        bottom.setPen(pg.mkPen(theme.MUTED))
        item.setLabel("bottom", "Quality", color=theme.MUTED)
        separator = pg.mkPen(255, 255, 255, 40)
        for row in range(1, self.channels):
            item.addItem(pg.InfiniteLine(row, angle=0, pen=separator))
        item.addItem(pg.InfiniteLine(0, angle=90, pen=pg.mkPen(theme.MUTED)))
        self.quality_dots = pg.ScatterPlotItem(
            x=[0.5] * self.channels,
            y=[self.channels - i - 0.5 for i in range(self.channels)],
            size=16, pen=pg.mkPen(theme.DARK, width=1),
            brush=[pg.mkBrush(theme.UNKNOWN)] * self.channels)
        item.addItem(self.quality_dots)
        self.quality_plot = item
        self.set_quality([quality.UNKNOWN] * self.channels)

    def set_quality(self, verdicts: list[str],
                    deviations=None) -> None:
        """Colour each channel's indicator by its quality verdict."""
        self.quality_dots.setBrush(
            [pg.mkBrush(QUALITY_COLOURS[v]) for v in verdicts])
        lines = []
        for i, verdict in enumerate(verdicts):
            line = f"CH{i + 1}: {QUALITY_TEXT[verdict]}"
            if deviations is not None and verdict != quality.UNKNOWN:
                line += f" ({deviations[i]:.1f} µV)"
            lines.append(line)
        low, high = quality.GOOD_RANGE_UV
        self.plot.setToolTip(
            "Signal quality: green while the raw EEG, filtered to "
            f"{quality.BAND[0]:g}-{quality.BAND[1]:g} Hz, varies by "
            f"{low:g}-{high:g} µV over the last {quality.WINDOW_S:g} s and "
            f"the raw signal swings by at most "
            f"{quality.RAW_SWING_LIMIT_UV / 1000:g} mV; red when flat, too "
            "noisy, drifting, or carrying only the noise common to all "
            "channels (no skin contact); grey while settling.\n\n"
            + "\n".join(lines))

    def _set_left_label(self) -> None:
        self.plot_item.setLabel(
            "left", f"EEG Amplitudes (−{self.scale_uv:g} … "
            f"+{self.scale_uv:g} µV)", color=theme.MUTED)

    def set_scale(self, half_range_uv: float) -> None:
        self.scale_uv = half_range_uv
        self._set_left_label()

    def clear(self) -> None:
        for curve in self.curves:
            curve.setData([], [])
        self.triggers.setData([], [])
        self.cursor.hide()

    def show_sweep(self, buffer: np.ndarray, total: int,
                   eeg: list[int], status: int | None) -> None:
        """Draw a SweepTap buffer that has seen ``total`` samples."""
        capacity = buffer.shape[0]
        if total == 0 or capacity != len(self.x):
            self.clear()
            return
        cursor = total % capacity
        filled = min(total, capacity)
        for row, column in enumerate(eeg[:self.channels]):
            values = buffer[:, column] / (2 * self.scale_uv)
            # Each trace stays inside its own row.
            y = (self.channels - row - 0.5) + np.clip(values, -0.5, 0.5)
            if filled < capacity:
                y[filled:] = np.nan
            # Break the line at the cursor, where new meets old.
            y[cursor] = np.nan
            self.curves[row].setData(self.x, y)
        if status is not None:
            slots = np.flatnonzero(buffer[:filled, status])
            xs = np.repeat(self.x[slots], 3)
            ys = np.tile([0.0, float(self.channels), np.nan], len(slots))
            xs[2::3] = np.nan
            self.triggers.setData(xs, ys)
        self.cursor.setValue(cursor / self.fs)
        self.cursor.show()
        self.axis.cursor = cursor / self.fs
        self.axis.sweep_start = (total - cursor) / self.fs
        self.axis.picture = None
        self.axis.update()
