"""Check for an SSH banner on port 22."""

import socket


def probe_ssh(host, timeout=3):
    host = host.strip()
    if not host:
        return dict(available=False, reason="Enter the router address first.")
    try:
        with socket.create_connection((host, 22), timeout=timeout) as connection:
            connection.settimeout(timeout)
            data = b""
            while len(data) < 1024:
                chunk = connection.recv(min(256, 1024 - len(data)))
                if not chunk:
                    break
                data += chunk
                for line in data.splitlines():
                    if line.startswith((b"SSH-2.0-", b"SSH-1.99-")):
                        return dict(
                            available=True,
                            reason="SSH service detected on port 22. Owner login is not yet verified.",
                        )
                if data.endswith(b"\n") and len(data.splitlines()) >= 5:
                    break
        return dict(
            available=False,
            reason="Port 22 answered, but an SSH service could not be identified.",
        )
    except ConnectionRefusedError:
        return dict(
            available=False,
            reason="Port 22 is closed or rejected. SSH may be disabled or blocked.",
        )
    except (OSError, TimeoutError):
        return dict(
            available=False,
            reason="SSH could not be reached on port 22. Check the address and LAN connection.",
        )
