"""The headset's g.Pype sources, real and simulated, which with OSCAR on
also emit the raw EEG.

g.Pype runs OSCAR inside a source's chain, between the link to the
device and the Sync after it, so that every output gets OSCAR's EEG. These
sources put :class:`~rhinorecorder.nodes.RawEegCopy` in front of OSCAR,
so the raw EEG comes through it untouched and in the same rows: raw files,
streams and views stay raw, and only the processed ones carry OSCAR, as
in Unicorn Recorder.
"""
from __future__ import annotations

from gprhino import RhinoHybridBlack

from .nodes import RawEegCopy
from .simulator import SimulatedHybridBlack


class _WithRawEeg:

    def middle_nodes(self) -> list:
        nodes = super().middle_nodes()
        # Without OSCAR there are no middle nodes, and the EEG is raw.
        return [RawEegCopy(name="raw_eeg"), *nodes] if nodes else nodes


class HeadsetSource(_WithRawEeg, RhinoHybridBlack):
    """The headset, over gpype-rhino."""


class SimulatedSource(_WithRawEeg, SimulatedHybridBlack):
    """The simulated headset."""
