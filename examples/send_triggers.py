"""Send triggers to Rhino Recorder's Trigger UDP Input.

    python send_triggers.py [ip] [port]

Sends 1, 2, ... 10, 1, 2, ... once a second until Ctrl+C, like Unicorn
Recorder's UDP Trigger Sender example. A trigger is its value as ASCII
text in one datagram; it appears in the TRIGGER column on the sample at
which it arrived.

The default port is 1000, Rhino Recorder's (and Unicorn Recorder's).
"""
import socket
import sys
import time

ip = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
port = int(sys.argv[2]) if len(sys.argv) > 2 else 1000

sender = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
print(f"Sending triggers to {ip}:{port}. Press Ctrl+C to stop.")
i = 0
try:
    while True:
        value = str(i % 10 + 1)
        sender.sendto(value.encode("ascii"), (ip, port))
        print(f"Sent trigger with value {value}")
        i += 1
        time.sleep(1)
except KeyboardInterrupt:
    pass
