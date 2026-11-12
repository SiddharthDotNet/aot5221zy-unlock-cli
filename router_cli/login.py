"""Sign in to the router and read its status page."""

from urllib.error import HTTPError

from .models import ActionResult
from .router_http import router_information, router_login
from .router_identity import MODEL


def cached_information(host, opener):
    """Return None when the status page requires a fresh login."""
    try:
        info = router_information(host, opener)
    except HTTPError as error:
        if error.code in (401, 403):
            return None
        raise
    if not info:
        return None
    return info


def login(session, io):
    password = ""
    try:
        connection = session.web_connection
        info = cached_information(session.host, connection[0]) if connection else None
        if info is None:
            session.web_connection = None
            password = io.password("Web password: ")
            if not password:
                raise ValueError("A password is required.")

            def log(message):
                io.write(str(message).replace(password, "[redacted]"))

            connection = router_login(session.host, session.web_user, password, log)
            if connection[0] is None:
                raise RuntimeError("Web login failed. Check the username and password.")
            info = router_information(session.host, connection[0])
        if info.get("model") != MODEL:
            session.web_connection = None
            raise RuntimeError("The router model could not be verified.")
        session.web_connection = connection
        session.remember_information(info, "web login")
        result = ActionResult("Web login", "SIGNED IN", "Device information refreshed.")
    except EOFError:
        raise
    except Exception as error:
        message = str(error).replace(password, "[redacted]") if password else str(error)
        result = ActionResult("Web login", "FAILED", message)
    session.last_result = result
    io.result(result)
