"""Receive Rhino Recorder's Raw or Processed Data LSL Output.

    python lsl_receiver.py

Lists the LSL streams on the network, lets you pick one, and prints its
samples, like Unicorn Recorder's LSL Receiver example. Needs pylsl.
"""
import pylsl

print("Scanning for LSL streams...")
streams = []
while not streams:
    streams = pylsl.resolve_streams(wait_time=2.0)
for i, info in enumerate(streams):
    print(f"[{i}] {info.name()}")
index = int(input("Select a stream by its [id] and press Enter: "))
inlet = pylsl.StreamInlet(streams[index])
info = inlet.info()
labels = []
channel = info.desc().child("channels").child("channel")
while not channel.empty():
    labels.append(channel.child_value("label"))
    channel = channel.next_sibling()
if labels:
    print(",".join(labels))
try:
    while True:
        sample, timestamp = inlet.pull_sample()
        print(",".join(f"{v:.3f}" for v in sample))
except KeyboardInterrupt:
    pass
