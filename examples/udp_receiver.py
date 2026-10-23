"""Receive Rhino Recorder's Raw or Processed Data UDP Output.

    python udp_receiver.py [port]

Each datagram is one sample: the included channels as comma-separated
text with three decimals, ending in a newline. The default port, 1001,
is the Processed Data UDP Output's; the raw output defaults to 1002.
"""
import socket
import sys

port = int(sys.argv[1]) if len(sys.argv) > 1 else 1001
receiver = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
receiver.bind(("0.0.0.0", port))
print(f"Listening on port {port}. Press Ctrl+C to stop.")
try:
    while True:
        data, _ = receiver.recvfrom(4096)
        values = [float(v) for v in data.decode("ascii").split(",")]
        print(", ".join(f"{v:9.3f}" for v in values))
except KeyboardInterrupt:
    pass
