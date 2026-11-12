"""Structured action outcomes shared by the CLI and full-screen interface."""

from dataclasses import dataclass


@dataclass
class ActionResult:
    title: str
    state: str
    message: str
    next_step: str = ""
