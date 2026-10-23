"""Load a Rhino Recorder CSV or BDF file, the counterpart of Unicorn
Recorder's MATLAB unicornrecorder_read.

    python read_recording.py RhinoRecorder_20261023_101500.csv

As a module::

    from read_recording import read
    rec = read("RhinoRecorder_20261023_101500.bdf")
    rec["data"]      # samples x channels, float
    rec["labels"]    # e.g. ["EEG 1", ..., "TRIG"]
    rec["triggers"]  # (sample index, value) of every trigger
"""
import sys

import numpy as np

SAMPLING_RATE = 250.0


def read(path: str) -> dict:
    if path.lower().endswith(".bdf"):
        import pyedflib
        try:
            reader = pyedflib.EdfReader(path)
        except OSError:
            # A recording cut short lacks its record count; restore it.
            from rhinorecorder.nodes import repair_bdf
            repair_bdf(path)
            reader = pyedflib.EdfReader(path)
        with reader:
            labels = reader.getSignalLabels()
            data = np.column_stack([reader.readSignal(i)
                                    for i in range(len(labels))])
            rate = reader.getSampleFrequency(0)
            info = {key: (value.decode() if isinstance(value, bytes)
                          else value).strip()
                    for key, value in (("subject", reader.patientcode),
                                       ("recording",
                                        reader.recording_additional),
                                       ("device", reader.equipment))}
            info["start"] = reader.getStartdatetime()
    else:
        with open(path) as f:
            comments = []
            line = f.readline()
            while line.startswith("#"):
                comments.append(line[1:].strip())
                line = f.readline()
            labels = line.strip().split(",")
        data = np.loadtxt(path, delimiter=",", comments="#",
                          skiprows=len(comments) + 1, ndmin=2)
        rate = SAMPLING_RATE
        info = {"notes": comments}
    triggers = []
    # TRIG; older files say TRIGGER, Unicorn Recorder's say STATUS.
    name = next((n for n in ("TRIG", "TRIGGER", "STATUS") if n in labels), None)
    if name:
        status = data[:, labels.index(name)]
        triggers = [(int(i), status[i]) for i in np.flatnonzero(status)]
    return {"data": data, "labels": labels, "sampling_rate": rate,
            "triggers": triggers, "info": info}


if __name__ == "__main__":
    rec = read(sys.argv[1])
    n, m = rec["data"].shape
    print(f"{n} samples x {m} channels at {rec['sampling_rate']:g} Hz "
          f"({n / rec['sampling_rate']:.1f} s)")
    print("channels:", ", ".join(rec["labels"]))
    print("triggers:", rec["triggers"][:20],
          "..." if len(rec["triggers"]) > 20 else "")
    for key, value in rec["info"].items():
        print(f"{key}: {value}")
