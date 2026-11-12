"""Store approved router SSH keys for the current user."""

import base64
import hashlib
import os
import tempfile
from pathlib import Path

import paramiko


def fingerprint(key):
    return "SHA256:" + base64.b64encode(hashlib.sha256(key.asbytes()).digest()).decode().rstrip("=")


def trust_path():
    base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".local" / "share")
    return base / "AOT5221ZYUnlockCLI" / "ssh_known_hosts"


class IdentityApprovalRequired(RuntimeError):
    def __init__(self, host, key, previous=None):
        self.host, self.key, self.previous = host, key, previous
        self.current_fingerprint = fingerprint(key)
        self.previous_fingerprint = fingerprint(previous) if previous else None
        super().__init__(
            f"Router identity {'changed' if previous else 'not yet trusted'} at {host}. "
            + (f"Previous fingerprint: {self.previous_fingerprint}. " if previous else "")
            + f"Presented {self.current_fingerprint}. Credentials were not sent."
        )


class RequireApprovalPolicy(paramiko.RejectPolicy):
    def missing_host_key(self, client, hostname, key):
        raise IdentityApprovalRequired(hostname, key)


def load_trust(client, bundled):
    # Locally approved keys take precedence over bundled entries.
    client.load_host_keys(str(bundled))
    path = trust_path()
    if path.exists():
        local = paramiko.HostKeys(str(path))
        keys = client.get_host_keys()
        for host in local:
            if host in keys:
                del keys[host]
            for kind, key in local[host].items():
                keys.add(host, kind, key)
    client.set_missing_host_key_policy(RequireApprovalPolicy())


def approve_identity(approval):
    """Call only after explicit user confirmation of this exact presented key."""
    path = trust_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    keys = paramiko.HostKeys(str(path)) if path.exists() else paramiko.HostKeys()
    if approval.host in keys:
        del keys[approval.host]
    keys.add(approval.host, approval.key.get_name(), approval.key)
    fd, temp = tempfile.mkstemp(prefix="ssh-trust-", dir=path.parent)
    os.close(fd)
    try:
        keys.save(temp)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
    return fingerprint(approval.key)
