"""Read the local default gateway and probe only a user-selected router."""

import ipaddress
import re
import socket
import subprocess
import sys

from .models import ActionResult
from .ssh_probe import probe_ssh


def default_gateway():
    try:
        if sys.platform == "win32":
            result = subprocess.run(
                ["route", "print", "-4"], capture_output=True, text=True, timeout=5, check=True
            )
            routes = re.findall(
                r"^\s*0\.0\.0\.0\s+0\.0\.0\.0\s+(\d+\.\d+\.\d+\.\d+)\s+\S+\s+(\d+)\s*$",
                result.stdout,
                re.MULTILINE,
            )
            candidates = [host for host, metric in sorted(routes, key=lambda item: int(item[1]))]
        else:
            result = subprocess.run(
                ["ip", "-4", "route", "show", "default"],
                capture_output=True,
                text=True,
                timeout=5,
                check=True,
            )
            candidates = re.findall(r"default via (\d+\.\d+\.\d+\.\d+)", result.stdout)
        for host in candidates:
            address = ipaddress.ip_address(host)
            if not address.is_unspecified and not address.is_loopback:
                return host
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    return None


def port_available(host, port):
    try:
        with socket.create_connection((host, port), timeout=2):
            return True
    except OSError:
        return False


def detect_access(host):
    return {
        "ssh": probe_ssh(host),
        "http": port_available(host, 80),
        "https": port_available(host, 443),
    }


def check_connectivity(host, session=None):
    result = detect_access(host)
    if session is not None:
        session.ssh_reachable = result["ssh"]["available"]
    lines = [
        result["ssh"]["reason"],
        f"Web port 80: {'reachable' if result['http'] else 'not reachable'}",
        f"Web port 443: {'reachable' if result['https'] else 'not reachable'}",
    ]
    return ActionResult("Connectivity", "CHECKED", "\n".join(lines))
