"""In-memory router session shared by terminal UI and direct commands."""

from dataclasses import dataclass, field
from datetime import datetime

from .models import ActionResult
from .router_identity import clean


@dataclass
class Session:
    host: str = ""
    web_user: str = "admin"
    ssh_user: str = ""
    web_connection: tuple | None = field(default=None, repr=False)
    information: dict = field(default_factory=dict)
    information_source: str = ""
    information_time: str = ""
    ssh_reachable: bool | None = None
    ssh_verified: bool = False
    last_result: ActionResult | None = None

    def remember_information(self, info, source):
        serial = info.get("serial") or self.information.get("serial")
        self.information = {
            key: clean(info[key])
            for key in ("model", "firmware", "hardware", "manufacturer", "uptime")
            if info.get(key)
        }
        self.information_source = source
        if serial:
            self.information["serial"] = clean(serial)
        self.information_time = datetime.now().strftime("%H:%M:%S")
        if source == "owner SSH":
            self.ssh_verified = True

    def reset_connection(self):
        self.web_connection = None
        self.information.clear()
        self.information_source = ""
        self.information_time = ""
        self.ssh_reachable = None
        self.ssh_verified = False
        self.last_result = None
