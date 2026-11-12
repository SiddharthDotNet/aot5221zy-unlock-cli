"""Download backups, enable LAN SSH, and unlock the supported web interface."""

import argparse
import getpass
import secrets
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

from .crypto import FIRMWARE_KEY, decrypt_config_bytes, encrypt_config_bytes
from .login import cached_information
from .models import ActionResult
from .router_http import router_download_backup, router_information, router_login, router_restore
from .router_identity import MODEL
from .ssh_config import apply_lan_ssh
from .ssh_probe import probe_ssh
from .ssh_trust import IdentityApprovalRequired, approve_identity
from .web_unlock import WebUnlock

FIRMWARE = "AOT5221ZY_R_2.29"


def record_result(session, title, state, message, next_step=""):
    if session is not None:
        session.last_result = ActionResult(title, state, message, next_step)


def confirm(message, token):
    print(message)
    return input(f"Type {token} to continue, or press Enter to cancel: ").strip() == token


def output_folder(path):
    folder = (
        Path(path)
        if path
        else Path("backups")
        / (datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(3))
    )
    folder.mkdir(mode=0o700, parents=True, exist_ok=False)
    return folder


def web_backup(host, user, password, output, log, connection=None, emit=print, info=None):
    opener, cookies = connection or router_login(host, user, password, log)
    if opener is None:
        raise RuntimeError("Web login failed. Check the username and password.")
    if info is None:
        info = router_information(host, opener)
    if info.get("model") != MODEL:
        raise RuntimeError(
            "The connected router could not be verified as AOT5221ZY. No configuration was changed."
        )
    encrypted = router_download_backup(host, opener, log)
    if encrypted is None:
        raise RuntimeError("No valid backup was received. Sign in again.")
    data = decrypt_config_bytes(encrypted, FIRMWARE_KEY)
    parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))
    xml = ET.fromstring(data, parser=parser)
    if xml.tag != "InternetGatewayDevice":
        raise RuntimeError(
            "Unexpected backup format. Expected an InternetGatewayDevice XML document."
        )
    folder = output_folder(output)
    (folder / "original.cfg").write_bytes(encrypted)
    (folder / "original.xml").write_bytes(data)
    emit(f"Backup saved: {folder.resolve()}")
    emit("Keep these files private. They may contain router passwords.")
    return opener, cookies, xml, folder, info


def unlock(host, user, password, log, on_information=None, on_result=None, io=None):
    emit = print if io is None else io.write
    ask_confirm = confirm if io is None else io.confirm

    def install():
        with WebUnlock(host, user, password, log) as router:
            if on_information is not None:
                try:
                    on_information(router.information(), "owner SSH")
                except Exception as error:
                    log(f"Device information could not be refreshed ({type(error).__name__}).")
            return router.install()

    try:
        result = install()
    except IdentityApprovalRequired as identity:
        emit(str(identity))
        if not ask_confirm(
            "Only trust this fingerprint if this is your router. A reset can change its identity.",
            "TRUST",
        ):
            if on_result is not None:
                on_result(
                    "CANCELLED",
                    "Router identity was not accepted. No SSH credentials were sent or keys saved.",
                    "Check the fingerprint before retrying Web unlock.",
                )
            emit("Cancelled. No SSH credentials were sent and no key was saved.")
            return 0
        approve_identity(identity)
        # A new handshake must match the approved key before credentials are sent.
        result = install()
    if not result["active"] or not result["enabled"]:
        raise RuntimeError("Could not verify the current unlock and startup settings.")
    if on_result is not None:
        on_result(
            "UNLOCKED",
            "Web controls are unlocked and automatic startup is enabled. No reboot was needed.",
            "Refresh the router web page to see the controls.",
        )
    emit("Web interface unlocked. Automatic startup enabled. No reboot was needed.")
    return 0


def main(argv=None, session=None, io=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        from .menu import run_menu

        return run_menu()
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog="Run without arguments (or use menu) for a session that remembers connection details.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    menu = sub.add_parser("menu", help="Compact keyboard menu with pinned device information")
    menu.add_argument("--host", default="", help="Router address to suggest for this session")
    menu.add_argument("--web-user", default="admin")
    menu.add_argument("--ssh-user", default="")
    for command, help_text in (
        ("detect", "Check web/SSH access without credentials or setting changes"),
        ("download", "Download and decrypt a fresh backup"),
        ("enable-ssh", "Prepare and optionally restore LAN SSH settings (reboots)"),
        ("unlock", "Enable the web interface and its startup helper"),
    ):
        item = sub.add_parser(command, help=help_text)
        item.add_argument("--host", required=True, help="Your router's LAN IP address")
        item.add_argument(
            "--user", help="Existing web username, or root-capable owner SSH username for unlock"
        )
        if command in ("download", "enable-ssh"):
            item.add_argument("--output", help="Save the files in a new directory")
        if command == "enable-ssh":
            item.add_argument(
                "--prepare-only",
                action="store_true",
                help="Save the edited XML/CFG without restoring or rebooting",
            )
    args = parser.parse_args(argv)
    if args.command == "menu":
        from .menu import run_menu
        from .session import Session

        return run_menu(Session(args.host, args.web_user, args.ssh_user))
    return run_action(**vars(args), session=session, io=io)


def run_action(command, host, user=None, output=None, prepare_only=False, session=None, io=None):
    emit = print if io is None else io.write
    ask = input if io is None else io.ask
    password_prompt = getpass.getpass if io is None else io.password
    ask_confirm = confirm if io is None else io.confirm
    try:
        if command == "detect":
            from .detection import check_connectivity

            result = check_connectivity(host, session)
            emit(result.message)
            if session is not None:
                session.last_result = result
            return 0
        if command == "enable-ssh" and probe_ssh(host)["available"]:
            if session is not None:
                session.ssh_reachable = True
            if prepare_only:
                message = "SSH is already reachable. File preparation was skipped."
                record_result(session, "Prepare SSH files", "SKIPPED", message)
                emit(message)
                return 0
            emit("SSH is already available on port 22.")
            record_result(
                session,
                "Enable SSH",
                "ALREADY ENABLED",
                "SSH is already available on port 22. No restore or reboot was needed.",
                "Select Unlock web interface.",
            )
            return 0
        if command == "enable-ssh" and prepare_only is None:
            choice = io.choose_ssh_setup()
            if choice is None:
                record_result(session, "SSH setup", "CANCELLED", "SSH setup cancelled.")
                return 0
            prepare_only = choice == "save"
        user = (
            user
            or ask(
                "Owner SSH username: " if command == "unlock" else "Router web username: "
            ).strip()
        )
        if not user:
            raise ValueError("A username is required.")
        connection = (
            session.web_connection
            if session is not None
            and command != "unlock"
            and session.host == host
            and session.web_user == user
            else None
        )
        info = cached_information(host, connection[0]) if connection else None
        if connection and info is None:
            session.web_connection = connection = None
        password = "" if connection else password_prompt("Router password: ")
        if not password and not connection:
            raise ValueError("A password is required.")

        def log(message):
            emit(
                str(message).replace(password, "[redacted]") if password else str(message),
                flush=True,
            )

        if command == "unlock":
            if not ask_confirm(
                "Enable the web debug flag now and install/enable its startup helper? This does not reboot.",
                "UNLOCK",
            ):
                record_result(
                    session,
                    "Web unlock",
                    "CANCELLED",
                    "No SSH connection was made and no router changes were applied.",
                )
                emit("Cancelled. No SSH connection was made.")
                return 0
            return unlock(
                host,
                user,
                password,
                log,
                session.remember_information if session is not None else None,
                lambda state, message, next_step: record_result(
                    session, "Web unlock", state, message, next_step
                ),
                io=io,
            )
        opener, cookies, xml, folder, info = web_backup(
            host, user, password, output, log, connection, emit=emit, info=info
        )
        if session is not None:
            session.web_connection = (opener, cookies)
            session.remember_information(info, "web session")
        if command == "download":
            record_result(
                session,
                "Download backup",
                "SAVED",
                f"Original encrypted and decrypted backups saved to:\n{folder.resolve()}",
                "Keep these files private.",
            )
            return 0
        if info.get("firmware") != FIRMWARE:
            raise RuntimeError(
                f"SSH preparation is verified only for {FIRMWARE}. The original backup is in {folder.resolve()}."
            )
        apply_lan_ssh(xml)
        edited = ET.tostring(xml, encoding="utf-8", xml_declaration=True)
        payload = encrypt_config_bytes(edited, FIRMWARE_KEY)
        (folder / "ssh-enabled.xml").write_bytes(edited)
        (folder / "ssh-enabled.cfg").write_bytes(payload)
        emit(
            "LAN SSH configuration prepared. Existing accounts and network settings are preserved."
        )
        if prepare_only:
            record_result(
                session,
                "Prepare SSH",
                "PREPARED",
                f"SSH configuration files saved to:\n{folder.resolve()}\nNo upload or reboot was performed.",
                "Open SSH setup when ready to restore.",
            )
            emit("Preparation only: no upload or reboot performed.")
            return 0
        if not ask_confirm(
            "Restoring this configuration REBOOTS the router and interrupts internet/Wi-Fi.",
            "REBOOT",
        ):
            record_result(
                session,
                "Enable SSH",
                "CANCELLED",
                f"Prepared files kept in {folder.resolve()}. No restore or reboot was performed.",
            )
            emit("Restore cancelled. Your prepared files are still on disk.")
            return 0
        # A restore always refreshes authentication after confirmation.
        if not password:
            password = password_prompt("Confirm router web password for restore: ")
            if not password:
                raise ValueError("A password is required to restore.")
        opener, cookies = router_login(host, user, password, log)
        if opener is None:
            raise RuntimeError("Could not refresh the web session. No restore performed.")
        router_restore(host, opener, payload, log)
        if session is not None:
            session.reset_connection()
        record_result(
            session,
            "Enable SSH",
            "RESTORE SUBMITTED",
            "Restore submitted. Wait for the router to restart before checking SSH.",
            "Use Check connectivity when the router returns.",
        )
        emit(
            "Restore submitted. Wait for the router to return, then connect on SSH port 22 using the existing owner account."
        )
        return 0
    except EOFError:
        if io is not None:
            raise
        emit("Input closed.", file=sys.stderr)
        return 130
    except KeyboardInterrupt:
        record_result(
            session,
            command,
            "STOPPED",
            "Check any operation already submitted before retrying.",
        )
        emit("\nStopped. Check any operation already submitted before retrying.", file=sys.stderr)
        return 130
    except Exception as error:
        # Do not print raw tracebacks or password-bearing transport messages.
        message = str(error)
        if "password" in locals() and password:
            message = message.replace(password, "[redacted]")
        if session is not None:
            if command == "unlock":
                session.ssh_verified = False
        record_result(
            session,
            command,
            "FAILED",
            message,
            "Review the error and check connection settings before retrying.",
        )
        emit(f"Error: {message}", file=sys.stderr)
        return 1
