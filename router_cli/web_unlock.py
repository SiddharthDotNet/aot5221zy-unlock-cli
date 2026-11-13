"""Owner SSH operations for the verified AOT5221ZY web unlock. Never reboot."""

import hashlib
import shlex
import uuid

import paramiko

from .paths import ASSETS as APP_ASSETS
from .router_identity import MODEL, log_identity, parse_ssh_identity
from .ssh_trust import IdentityApprovalRequired, load_trust

ASSETS = APP_ASSETS / "web_unlock"
BASE = "/etc/router-web-unlock"
SERVICE = "/etc/init.d/zzzz_router_web_unlock"
LINK = "/etc/rc.d/S99zzzz_router_web_unlock"
# Verified ccctest builds: AOT5221ZY_R_2.29 and AOT5221ZY_R_2.26.
UTILITY_MD5S = (
    "9af374bfc32752227fc5e71baabdfd1d",
    "bc888e8e64d1e5ab0b64ff8589b54fe8",
)


class WebUnlock:
    def __init__(self, host, username, password, log=lambda message: None):
        if not host.strip() or not username.strip() or not password:
            raise ValueError("Enter the SSH address, username, and password.")
        self.host, self.username, self.password = (
            host.strip(),
            username.strip(),
            password,
        )
        self.log = log
        self.client = None

    def __enter__(self):
        self.log("Opening owner SSH connection...")
        self.client = paramiko.SSHClient()
        load_trust(self.client, ASSETS / "ssh_known_hosts")
        try:
            self.client.connect(
                self.host,
                username=self.username,
                password=self.password,
                look_for_keys=False,
                allow_agent=False,
                timeout=8,
                banner_timeout=8,
                auth_timeout=8,
            )
            if b"uid=0" not in self.run("id"):
                raise RuntimeError(
                    "The unlock needs an existing owner SSH account with root access."
                )
            self.log("Connected over SSH. Router identity verified.")
            info = self.information()
            if info.get("model") != MODEL:
                raise RuntimeError(f"Could not verify the router as {MODEL}. Unlock cancelled.")
            log_identity(info, self.log, "SSH")
        except paramiko.BadHostKeyException as error:
            self.client.close()
            self.password = ""
            raise IdentityApprovalRequired(error.hostname, error.key, error.expected_key) from None
        except Exception:
            self.client.close()
            self.password = ""
            raise
        self.password = ""
        return self

    def __exit__(self, *args):
        self.client.close()

    def information(self):
        found = hashlib.md5(self.read("/usr/bin/ccctest")).hexdigest()
        if found not in UTILITY_MD5S:
            raise RuntimeError(
                f"Unsupported vendor utility: /usr/bin/ccctest MD5 is {found}, expected one of {", ".join(UTILITY_MD5S)}. "
                "This firmware differs from the verified one."
            )
        path = "/tmp/router-info-" + uuid.uuid4().hex + ".ccc"
        payload = (
            "RDMNAME config;\nREQUEST;\nSEL InternetGatewayDevice.DeviceInfo;\n"
            "GET ModelName;\nGET SoftwareVersion;\nGET HardwareVersion;\nGET Manufacturer;\nGET SerialNumber;\nSEND;\n"
        )
        self.upload(path, payload.encode())
        try:
            data = self.run("/usr/bin/ccctest -f " + path + " -n router_gui_info")
        finally:
            self.run("rm -f " + path)
        info = parse_ssh_identity(data.decode(errors="replace"))
        info["uptime"] = self.read("/proc/uptime").decode().split()[0] + " seconds"
        return info

    def run(self, command, timeout=20):
        _, out, err = self.client.exec_command(command, timeout=timeout)
        data, error = out.read(2_000_000), err.read(10_000)
        if out.channel.recv_exit_status():
            # Commands contain only fixed paths, hashes and flag values, never credentials.
            raise RuntimeError(
                "Router command failed: " + command + "\n" + error.decode(errors="replace")
            )
        return data

    def read(self, path):
        return self.run("cat " + shlex.quote(path))

    def exists(self, path):
        quoted = shlex.quote(path)
        return (
            self.run("if [ -e " + quoted + " ] || [ -L " + quoted + " ]; then echo yes; fi").strip()
            == b"yes"
        )

    def upload(self, path, data):
        incoming, out, err = self.client.exec_command("cat > " + shlex.quote(path), timeout=20)
        incoming.write(data)
        incoming.flush()
        incoming.channel.shutdown_write()
        out.read()
        if out.channel.recv_exit_status() or self.read(path) != data:
            raise RuntimeError("Could not verify uploaded file: " + path)

    def compatible(self):
        if hashlib.md5(self.read("/usr/bin/ccctest")).hexdigest() not in UTILITY_MD5S:
            raise RuntimeError(
                "This firmware does not match the verified vendor utility. No changes applied."
            )
        self.log("Router utility version checked.")

    def flag(self, value=None):
        if hashlib.md5(self.read("/usr/bin/ccctest")).hexdigest() not in UTILITY_MD5S:
            raise RuntimeError("Unsupported router utility.")
        lines = ["RDMNAME config;", "REQUEST;", "SEL InternetGatewayDevice.DeviceInfo;"]
        if value is not None:
            if value not in (0, 1):
                raise ValueError("Invalid web flag")
            lines.append(f"SET_NO_BE X_5067F0_DebugVersionFlag boolean {value};")
        lines += ["GET X_5067F0_DebugVersionFlag;", "SEND;"]
        path = "/tmp/router-gui-" + uuid.uuid4().hex + ".ccc"
        self.upload(path, ("\n".join(lines) + "\n").encode())
        try:
            data = self.run("/usr/bin/ccctest -f " + path + " -n router_gui_read")
        finally:
            self.run("rm -f " + path)
        if b"transaction successful" not in data or b"fail" in data.lower():
            raise RuntimeError("The router did not accept the web flag request.")
        if b"Value=1" in data:
            actual = 1
        elif b"Value=0" in data:
            actual = 0
        else:
            raise RuntimeError("The router returned an unrecognized web flag value.")
        if value is not None and value != actual:
            raise RuntimeError("Web flag readback did not match the requested value.")
        return bool(actual)

    def payloads(self):
        return {
            BASE + "/apply.sh": (ASSETS / "apply.sh").read_bytes(),
            SERVICE: (ASSETS / "zzzz_router_web_unlock").read_bytes(),
        }

    def owned_installation(self):
        # Only this tool's exact debug-flag-only scripts may be managed.
        payloads = self.payloads()
        if not self.exists(SERVICE) or self.read(SERVICE) != payloads[SERVICE]:
            raise RuntimeError("Installation is missing or differs from this app: " + SERVICE)
        path = BASE + "/apply.sh"
        if not self.exists(path):
            raise RuntimeError("Missing installed apply script.")
        if self.read(path) != payloads[path]:
            raise RuntimeError(
                "Existing unlock installation differs from this version. This version cannot upgrade those files."
            )
        if self.exists(LINK):
            if self.run("readlink " + LINK).strip() != b"../init.d/zzzz_router_web_unlock":
                raise RuntimeError("The startup link points to an unexpected file.")
        return "debug-flag-only"

    def status(self):
        self.compatible()
        installed = self.exists(SERVICE) or self.exists(BASE)
        trusted = False
        kind = "not-installed"
        if installed:
            try:
                kind = self.owned_installation()
                trusted = True
            except RuntimeError:
                self.log("The installed service differs from the bundled version.")
        result = dict(
            installed=installed,
            verified=trusted,
            enabled=self.exists(LINK),
            active=self.flag(),
            mode=kind,
            uptime=self.read("/proc/uptime").decode().split()[0],
        )
        self.log(
            "Status: "
            + ("web unlock active" if result["active"] else "web unlock inactive")
            + ", startup "
            + ("enabled" if result["enabled"] else "disabled")
            + "."
        )
        return result

    def install(self):
        self.compatible()
        payloads = self.payloads()
        existing = self.exists(SERVICE) or self.exists(BASE) or self.exists(LINK)
        if existing:
            self.owned_installation()
            self.log("Re-enabling the existing installation.")
        else:
            self.log("Installing persistent startup files...")
            self.run("mkdir " + BASE)
            try:
                for path, data in payloads.items():
                    self.upload(path, data)
                self.run("chmod 700 " + BASE + " " + BASE + "/apply.sh " + SERVICE)
                self.run("/bin/sh -n " + BASE + "/apply.sh && /bin/sh -n " + SERVICE)
            except Exception:
                self.log(
                    "Installation incomplete. Check the reported file before retrying. Startup is still disabled."
                )
                raise
        self.log("Applying the unlock. No reboot needed.")
        self.run(SERVICE + " start", timeout=90)
        if not self.flag():
            raise RuntimeError("The service ran but the flag is not active.")
        self.run(SERVICE + " enable")
        self.run("sync")
        self.log(
            "Unlock installed and enabled. After future boots, allow two minutes for automatic activation."
        )
        return self.status()
