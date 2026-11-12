"""Read router status, download backups and submit restores over HTTP."""

import hashlib
import http.client
import http.cookiejar
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from .router_identity import parse_web_identity


class SessionExpiredError(RuntimeError):
    """The router requires a fresh login before this operation can continue."""


class RouterRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        current = urllib.parse.urlsplit(req.full_url)
        target = urllib.parse.urlsplit(newurl)
        if (current.scheme, current.netloc.lower()) != (target.scheme, target.netloc.lower()):
            raise RuntimeError("The router redirected the request to a different address.")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def router_login(router_ip, username, password, log):
    login_url = f"http://{router_ip}/cgi-bin/login_advance.cgi"
    cookie_jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(
        RouterRedirectHandler(), urllib.request.HTTPCookieProcessor(cookie_jar)
    )

    log(f"Connecting to {router_ip} ...")
    resp = opener.open(urllib.request.Request(login_url), timeout=10)
    page = resp.read().decode("utf-8", errors="ignore")

    sid_match = re.search(r"var sid = '([^']+)'", page)
    if not sid_match:
        log("ERROR: Could not find SID on login page.")
        return None, None
    sid = sid_match.group(1)
    log("Login challenge received.")

    temp_pwd = urllib.parse.quote(password, safe="")
    temp_pwd = re.sub(r"%[0-9A-F]{2}", lambda m: m.group(0).lower(), temp_pwd)
    pwd_hash = hashlib.md5(f"{temp_pwd}:{sid}".encode("latin-1")).hexdigest()

    post_data = urllib.parse.urlencode(
        {
            "Loginuser": username,
            "LoginPasswordValue": pwd_hash,
            "LoginSidValue": sid,
            "submitValue": "1",
            "Prestige_Login": "Login",
            "fake_username": "",
            "fake_pass": "",
        }
    ).encode()

    opener.open(urllib.request.Request(login_url, data=post_data), timeout=10)

    for cookie in cookie_jar:
        if cookie.name == "COOKIE_SESSION_KEY":
            log("Login successful.")
            return opener, cookie_jar

    log("ERROR: Login failed (no session cookie returned). Check username/password.")
    return None, None


def router_restore(router_ip, opener, encrypted_bytes, log):
    backup_url = f"http://{router_ip}/cgi-bin/backupRestore.cgi"
    boundary = "----WebKitFormBoundary" + os.urandom(16).hex()

    body = [
        f"--{boundary}".encode(),
        b'Content-Disposition: form-data; name="tools_FW_UploadFile"; filename="config.cfg"',
        b"Content-Type: application/octet-stream",
        b"",
        encrypted_bytes,
        f"--{boundary}".encode(),
        b'Content-Disposition: form-data; name="postflag"',
        b"",
        b"1",
        f"--{boundary}--".encode(),
        b"",
    ]

    req = urllib.request.Request(
        backup_url,
        data=b"\r\n".join(body),
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Referer": backup_url,
        },
    )

    log("Uploading config ...")
    try:
        with opener.open(req, timeout=15) as response:
            if "login" in urllib.parse.urlparse(response.geturl()).path.lower():
                raise SessionExpiredError("Your router session expired. Please connect again.")
        log("Upload accepted.")
    except (ConnectionResetError, http.client.RemoteDisconnected) as error:
        raise RuntimeError(
            "The router disconnected before confirming the restore. It may be rebooting. "
            "Wait for it to return and check its settings before retrying."
        ) from error

    log("Restore submitted. Wait about a minute before reconnecting.")


def router_download_backup(router_ip, opener, log):
    """Trigger backup generation on the router and download the encrypted .cfg."""
    backup_url = f"http://{router_ip}/cgi-bin/backupRestore.cgi"
    romfile_url = f"http://{router_ip}/romfile.cfg"

    log("Requesting a backup...")
    post_data = urllib.parse.urlencode({"configFilter": "1"}).encode()
    opener.open(
        urllib.request.Request(backup_url, data=post_data, headers={"Referer": backup_url}),
        timeout=10,
    )

    log("Waiting for the backup...")
    time.sleep(3)

    log("Downloading backup file...")
    resp = opener.open(
        urllib.request.Request(romfile_url, headers={"Referer": backup_url}), timeout=15
    )
    backup_data = resp.read()

    if backup_data[:8] != b"Salted__":
        log(
            "ERROR: Downloaded file is not an encrypted backup (router may have returned an error page)."
        )
        return None

    log(f"Downloaded {len(backup_data)} bytes.")
    return backup_data


def router_information(address, opener):
    request = urllib.request.Request(
        f"http://{address}/cgi-bin/statusview.cgi",
        headers={"Referer": f"http://{address}/cgi-bin/indexmain.cgi"},
    )
    with opener.open(request, timeout=8) as response:
        return parse_web_identity(response.read(200_000).decode("utf-8", errors="replace"))
