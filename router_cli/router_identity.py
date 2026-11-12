"""Read device details from web and SSH status output."""

import html
import re

MODEL = "AOT5221ZY"
FIELDS = {
    "model": "Model",
    "firmware": "Firmware",
    "hardware": "Hardware",
    "manufacturer": "Manufacturer",
    "uptime": "Uptime",
}


def clean(value):
    return " ".join(str(value).split())[:160]


def parse_web_identity(page):
    info = {}
    for key, element in [
        ("model", "ModelName_ConnectionStatus"),
        ("firmware", "MLG_FirmwareVersion_ConnectionStatus"),
        ("uptime", "MLG_Home_SysUp"),
    ]:
        match = re.search(
            r"<span\b[^>]*\bid=[\'\"]"
            + element
            + r"[\'\"][^>]*>.*?</span>.*?</td>\s*<td\b[^>]*>(.*?)</td>",
            page,
            re.I | re.S,
        )
        if match:
            value = clean(html.unescape(re.sub(r"<[^>]+>", " ", match.group(1))))
            if key == "uptime":
                parts = re.findall(r"\d+", value)
                if len(parts) == 3:
                    value = f"{parts[0]}d {parts[1]}h {parts[2]}m"
            if value:
                info[key] = value
    for row in re.findall(r"<tr\b[^>]*>(.*?)</tr>", page, re.I | re.S):
        cells = re.findall(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", row, re.I | re.S)
        if len(cells) < 2:
            continue
        label, value = (clean(html.unescape(re.sub(r"<[^>]+>", "", cell))) for cell in cells[:2])
        if (
            re.fullmatch(
                r"(?:(?:device|router|system)\s+)?serial\s*(?:number|no\.?)\s*:?", label, re.I
            )
            and value
        ):
            info["serial"] = value
            break
    return info


def parse_ssh_identity(output):
    info = {}
    for key, leaf in [
        ("model", "ModelName"),
        ("firmware", "SoftwareVersion"),
        ("hardware", "HardwareVersion"),
        ("manufacturer", "Manufacturer"),
        ("serial", "SerialNumber"),
    ]:
        match = re.search(
            r"GET " + leaf + r": success\s+type=string\s+SizeOfValue=\d+\s+Value=([^\r\n]*)",
            output,
        )
        if match:
            info[key] = clean(match.group(1))
    return info


def log_identity(info, log, transport):
    log(f"Router information ({transport}):")
    for key, label in FIELDS.items():
        if info.get(key):
            log(f"  {label}: {clean(info[key])}")
    if not info:
        log("  Device details were not supplied by this interface.")
    if transport == "web" and not info.get("hardware"):
        log("  Hardware revision is available through owner SSH, not this web status page.")
