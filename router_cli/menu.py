"""Compact keyboard menu with pinned device information and inline results."""

import asyncio

from prompt_toolkit.application import Application
from prompt_toolkit.data_structures import Point
from prompt_toolkit.filters import Condition
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.key_binding.bindings.focus import focus_next, focus_previous
from prompt_toolkit.layout import Dimension, Float, FloatContainer, HSplit, Layout, VSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.widgets import Button, Dialog, Frame, Label, TextArea

from . import commands
from .cursor import InputCursor
from .detection import default_gateway
from .models import ActionResult
from .session import Session
from .theme import MENU_STYLE

ICON_WIDTH = 9
CREDIT = "© 2026 Siddharth.net"

ACTIONS = [
    ("login", "Connect to router", "Read device information"),
    ("detect", "Check connectivity", "Check web and SSH ports"),
    ("download", "Download and decrypt backup", "Save a private backup"),
    ("enable-ssh", "SSH setup", "Check SSH and choose a setup option"),
    ("unlock", "Unlock web interface", "Applies now and on future boots"),
]


class MenuIO:
    def __init__(self, menu):
        self.menu = menu
        self.secrets = []

    def write(self, message="", **kwargs):
        text = str(message)
        for secret in self.secrets:
            text = text.replace(secret, "[redacted]")
        self.menu.loop.call_soon_threadsafe(self.menu.log, text)

    def ask(self, label):
        value = asyncio.run_coroutine_threadsafe(self.menu.prompt(label), self.menu.loop).result()
        if value is None:
            raise EOFError()
        return value

    def password(self, label):
        value = asyncio.run_coroutine_threadsafe(
            self.menu.prompt(label, secret=True), self.menu.loop
        ).result()
        if value is None:
            raise EOFError()
        if value:
            self.secrets.append(value)
        return value

    def confirm(self, message, token):
        value = asyncio.run_coroutine_threadsafe(
            self.menu.prompt(message, token=token), self.menu.loop
        ).result()
        return value is not None and value.strip() == token

    def result(self, result):
        self.menu.session.last_result = result
        self.menu.loop.call_soon_threadsafe(self.menu.app.invalidate)

    def choose_ssh_setup(self):
        return asyncio.run_coroutine_threadsafe(self.menu.ssh_setup(), self.menu.loop).result()


class RouterMenu:
    def __init__(self, session=None, input=None, output=None):
        self.session = session or Session()
        self.selected = 0
        self.busy = False
        self.dialog = None
        self.caret_visible = True
        self.loop = None
        self.lines = []
        self.activity = TextArea(
            text="No activity yet.",
            read_only=True,
            scrollbar=True,
            wrap_lines=True,
            focusable=True,
            style="class:activity",
        )
        self.list_control = FormattedTextControl(
            self.menu_text,
            focusable=True,
            show_cursor=False,
            get_cursor_position=lambda: Point(x=0, y=self.selected),
        )
        self.menu_window = Window(
            self.list_control,
            height=len(ACTIONS),
            dont_extend_height=True,
            cursorline=True,
            style="class:action-menu",
        )
        self.container = FloatContainer(
            floats=[],
            content=HSplit(
                [
                    VSplit(
                        [
                            Window(
                                FormattedTextControl(self.brand_icon),
                                width=ICON_WIDTH,
                                height=6,
                                style="class:header",
                            ),
                            Window(
                                FormattedTextControl(self.header), height=6, style="class:header"
                            ),
                        ]
                    ),
                    Frame(
                        HSplit(
                            [
                                Window(
                                    FormattedTextControl(
                                        [
                                            (
                                                "class:column",
                                                "  ACTION                            DETAILS",
                                            )
                                        ]
                                    ),
                                    height=1,
                                    style="class:column",
                                ),
                                self.menu_window,
                            ]
                        ),
                        style="class:section",
                    ),
                    Window(
                        FormattedTextControl(self.result_text),
                        height=Dimension(min=3, preferred=5, max=7),
                        wrap_lines=True,
                    ),
                    Frame(self.activity, title=" Activity ", style="class:section"),
                    Window(FormattedTextControl(self.footer), height=1, style="class:footer"),
                ]
            ),
        )
        keys = KeyBindings()
        normal = Condition(lambda: self.dialog is None)

        navigation = Condition(
            lambda: (
                self.dialog is None
                and not self.busy
                and self.app.layout.has_focus(self.menu_window)
            )
        )

        @keys.add("up", filter=navigation)
        def up(event):
            self.selected = (self.selected - 1) % len(ACTIONS)

        @keys.add("down", filter=navigation)
        def down(event):
            self.selected = (self.selected + 1) % len(ACTIONS)

        @keys.add("enter", filter=navigation)
        def enter(event):
            self.start(ACTIONS[self.selected][0])

        @keys.add("f2", filter=normal)
        def settings(event):
            self.start("connection")

        @keys.add("f5", filter=normal)
        def refresh(event):
            self.start("login")

        @keys.add("q", filter=normal)
        @keys.add("c-c", filter=normal)
        def quit_app(event):
            if not self.busy:
                event.app.exit()
            else:
                self.log("Finish or cancel the current action before exiting.")

        @keys.add("tab", filter=normal)
        def tab(event):
            event.app.layout.focus(
                self.activity if event.app.layout.has_focus(self.menu_window) else self.menu_window
            )

        @keys.add("up", filter=Condition(lambda: self.dialog is not None), eager=True)
        def previous_field(event):
            focus_previous(event)

        @keys.add("down", filter=Condition(lambda: self.dialog is not None), eager=True)
        def next_field(event):
            focus_next(event)

        @keys.add("escape", filter=Condition(lambda: self.dialog is not None))
        def cancel(event):
            self.dismiss(None)

        self.app = Application(
            layout=Layout(self.container, focused_element=self.menu_window),
            key_bindings=keys,
            full_screen=True,
            mouse_support=False,
            input=input,
            output=output,
            style=MENU_STYLE,
        )

    def brand_icon(self):
        return [("class:brand-icon", "\n  |   |\n  +---+\n  |o o|\n  +---+\n")]

    def header(self):
        s = self.session
        info = s.information
        title = " AOT5221ZY"
        subtitle = "  Unlock CLI"
        gap = self.app.output.get_size().columns - ICON_WIDTH - len(title + subtitle + CREDIT) - 1
        credit = " " * gap + CREDIT if gap >= 4 else ""
        return [
            ("class:title", title),
            ("class:muted", subtitle + credit + "\n"),
            ("class:muted", " Router "),
            ("class:title", s.host or "not configured"),
            ("class:muted", "    Web user "),
            ("", s.web_user),
            ("class:muted", "    SSH user "),
            ("", (s.ssh_user or "not set") + "\n"),
            ("class:muted", " Model "),
            ("", info.get("model", "-")),
            ("class:muted", "    Firmware "),
            ("", info.get("firmware", "-")),
            ("class:muted", "    Serial "),
            ("", info.get("serial", "-") + "\n"),
            ("class:muted", " Hardware "),
            ("", info.get("hardware", "-")),
            ("class:muted", "    Uptime "),
            ("", info.get("uptime", "-") + "\n"),
            ("class:muted", " Web "),
            (
                "class:good" if s.web_connection else "class:muted",
                "Signed in" if s.web_connection else "Not signed in",
            ),
            ("class:muted", "    SSH "),
            (
                "class:good" if s.ssh_verified else "class:muted",
                "Owner verified"
                if s.ssh_verified
                else {True: "Reachable", False: "Unreachable", None: "Unchecked"}[s.ssh_reachable],
            ),
            ("class:muted", f"    Last read {s.information_time or '-'}\n"),
        ]

    def menu_text(self):
        rows = []
        for index, (action, label, detail) in enumerate(ACTIONS):
            if action == "login" and self.session.web_connection:
                label = "Refresh device info"
            selected = index == self.selected
            marker = ">" if selected else " "
            rows.append(("", f" {marker} {label:<33} {detail}\n"))
        return rows

    def result_text(self):
        r = self.session.last_result
        if not r:
            return [("class:muted", " READY  Select an action with Up/Down and Enter.\n")]
        style = (
            "class:error"
            if r.state in ("FAILED", "STOPPED")
            else "class:warning"
            if r.state in ("CANCELLED", "WORKING", "RESTORE SUBMITTED", "UNVERIFIED")
            else "class:good"
        )
        return [
            (style, f" {r.title.upper()}  |  {r.state}\n"),
            ("", r.message + "\n"),
            ("class:muted", ("Next: " + r.next_step) if r.next_step else ""),
        ]

    def footer(self):
        parts = []
        for key, label in (
            (" ↑↓ ", " Select  "),
            (" Enter ", " Run  "),
            (" F5 ", " Refresh  " if self.session.web_connection else " Connect  "),
            (" F2 ", " Settings  "),
            (" Tab ", " Log  "),
            (" Q ", " Quit  "),
        ):
            parts.extend([("class:hotkey", key), ("class:muted", label)])
        parts.append(
            (
                "class:warning" if self.busy else "class:muted",
                " ● WORKING" if self.busy else " ○ READY",
            )
        )
        return parts

    def log(self, text):
        self.lines.extend(str(text).splitlines())
        self.lines = self.lines[-200:]
        self.activity.text = "\n".join(self.lines)
        self.activity.buffer.cursor_position = len(self.activity.text)
        self.app.invalidate()

    def dismiss(self, value):
        if self.dialog:
            future, fields = self.dialog
            for field in fields:
                field.text = ""
            self.container.floats.clear()
            self.dialog = None
            self.app.layout.focus(self.menu_window)
            if not future.done():
                future.set_result(value)
            self.app.invalidate()

    def input_field(self, text="", secret=False, width=None):
        field = TextArea(
            text=text,
            password=secret,
            multiline=False,
            width=width,
            input_processors=[InputCursor(lambda: self.caret_visible)],
        )
        field.window.always_hide_cursor = Condition(lambda: True)
        field.window.style = lambda: (
            "class:text-area class:input-field.focused"
            if self.app.layout.has_focus(field)
            else "class:text-area class:input-field"
        )
        return field

    async def show_dialog(self, dialog, focus, fields=()):
        future = asyncio.get_running_loop().create_future()
        self.container.floats.append(Float(content=dialog))
        self.dialog = (future, fields)
        self.app.layout.focus(focus)
        self.app.invalidate()
        if not fields:
            return await future

        loop = asyncio.get_running_loop()
        timer = None

        def blink():
            nonlocal timer
            if not future.done() and any(self.app.layout.has_focus(field) for field in fields):
                self.caret_visible = not self.caret_visible
                self.app.invalidate()
                timer = loop.call_later(0.55, blink)

        def restart_blink(sender=None):
            nonlocal timer
            if timer is not None:
                timer.cancel()
            self.caret_visible = True
            if not future.done() and any(self.app.layout.has_focus(field) for field in fields):
                timer = loop.call_later(0.55, blink)

        restart_blink()
        self.app.key_processor.after_key_press += restart_blink
        try:
            return await future
        finally:
            self.app.key_processor.after_key_press -= restart_blink
            if timer is not None:
                timer.cancel()

    async def ssh_setup(self):
        save = Button("Save files only", width=19, handler=lambda: self.dismiss("save"))
        dialog = Dialog(
            title="SSH setup",
            body=Label("SSH was not detected. Enabling it requires a reboot."),
            buttons=[
                save,
                Button("Enable SSH and reboot", width=25, handler=lambda: self.dismiss("enable")),
                Button("Cancel", handler=lambda: self.dismiss(None)),
            ],
            width=Dimension(preferred=72),
        )
        return await self.show_dialog(dialog, save)

    async def prompt(self, message, secret=False, token=""):
        error = Label("")
        field = self.input_field(secret=secret, width=Dimension(preferred=55))

        def accept():
            value = field.text
            if token and value.strip() != token:
                error.text = f"Type {token}, or cancel."
                return
            if not value and not token:
                error.text = "Enter a value, or cancel."
                return
            self.dismiss(value)

        field.buffer.accept_handler = lambda buffer: accept()
        body = HSplit(
            [Label(message), Label(f"Type {token} to confirm." if token else ""), field, error],
            padding=1,
        )
        dialog = Dialog(
            title="Confirm action" if token else "Login",
            body=body,
            buttons=[
                Button("Continue", handler=accept),
                Button("Cancel", handler=lambda: self.dismiss(None)),
            ],
            width=Dimension(preferred=70),
        )
        return await self.show_dialog(dialog, field, [field])

    async def connection(self, action="connection"):
        gateway = await asyncio.to_thread(default_gateway) if not self.session.host else ""
        host = self.input_field(text=self.session.host or gateway or "")
        web = self.input_field(text=self.session.web_user)
        ssh = self.input_field(text=self.session.ssh_user)
        error = Label("")

        fields = [host]
        controls = [Label("Router address (check the suggested gateway)"), host]
        if action not in ("detect", "unlock"):
            fields.append(web)
            controls.extend([Label("Web username"), web])
        if action == "connection":
            fields.append(ssh)
            controls.extend([Label("Owner SSH username (optional)"), ssh])

        def accept():
            if not host.text.strip() or (web in fields and not web.text.strip()):
                error.text = (
                    "Enter the router address."
                    if not host.text.strip()
                    else "Enter the web username."
                )
                return
            self.dismiss((host.text.strip(), web.text.strip(), ssh.text.strip()))

        for current, following in zip(fields, fields[1:]):
            current.buffer.accept_handler = lambda buffer, target=following: (
                self.app.layout.focus(target) or True
            )
        fields[-1].buffer.accept_handler = lambda buffer: accept() or True

        dialog = Dialog(
            title="Connection settings" if action == "connection" else "Router details",
            body=HSplit(
                [*controls, Label("Up/Down: fields and buttons   Tab: next"), error],
                padding=1,
            ),
            buttons=[
                Button("Save" if action == "connection" else "Continue", handler=accept),
                Button("Cancel", handler=lambda: self.dismiss(None)),
            ],
            width=Dimension(preferred=72),
        )
        values = await self.show_dialog(dialog, host, fields)
        if values is None:
            self.session.last_result = ActionResult(
                "Connection", "CANCELLED", "Connection settings were not changed."
            )
            return False
        h, w, s = values
        if (h, w) != (self.session.host, self.session.web_user):
            self.session.reset_connection()
        if s != self.session.ssh_user:
            self.session.ssh_verified = False
        self.session.host, self.session.web_user, self.session.ssh_user = values
        if action == "connection":
            self.session.last_result = ActionResult(
                "Connection", "UPDATED", "Details saved for this session only."
            )
        return True

    def start(self, action):
        if self.busy:
            return
        self.busy = True
        self.session.last_result = ActionResult(action, "WORKING", "Working...")
        self.app.create_background_task(self.perform(action))

    async def perform(self, action):
        bridge = MenuIO(self)
        try:
            if action == "connection":
                await self.connection()
                return
            if not self.session.host and not await self.connection(action):
                return
            if action == "login":
                from .login import login

                await asyncio.to_thread(login, self.session, bridge)
            else:
                if action == "unlock" and not self.session.ssh_user:
                    self.session.ssh_user = (
                        await self.prompt("Existing root-capable SSH username") or ""
                    )
                    if not self.session.ssh_user:
                        raise EOFError()
                await asyncio.to_thread(
                    commands.run_action,
                    action,
                    self.session.host,
                    user=self.session.ssh_user if action == "unlock" else self.session.web_user,
                    prepare_only=None if action == "enable-ssh" else False,
                    session=self.session,
                    io=bridge,
                )
        except EOFError:
            self.session.last_result = ActionResult(
                action,
                "CANCELLED",
                "Action cancelled.",
            )
        except Exception as error:
            message = str(error)
            for secret in bridge.secrets:
                message = message.replace(secret, "[redacted]")
            self.session.last_result = ActionResult(action, "FAILED", message)
        finally:
            bridge.secrets.clear()
            self.busy = False
            self.app.invalidate()

    async def run_async(self):
        self.loop = asyncio.get_running_loop()
        return await self.app.run_async()


def run_menu(session=None):
    asyncio.run(RouterMenu(session).run_async())
    return 0
