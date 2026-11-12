"""A visible input caret independent of the terminal's own cursor colour."""

from prompt_toolkit.application.current import get_app
from prompt_toolkit.layout.processors import Processor, Transformation
from prompt_toolkit.layout.utils import explode_text_fragments


class InputCursor(Processor):
    def __init__(self, is_visible):
        self.is_visible = is_visible

    def apply_transformation(self, transformation_input):
        item = transformation_input
        if (
            not self.is_visible()
            or not get_app().layout.has_focus(item.buffer_control)
            or item.lineno != item.document.cursor_position_row
        ):
            return Transformation(item.fragments)
        fragments = explode_text_fragments(item.fragments)
        index = item.source_to_display(item.document.cursor_position_col)
        while len(fragments) <= index:
            fragments.append(("", " "))
        style, text, *extra = fragments[index]
        fragments[index] = (style + " class:input-cursor", text, *extra)
        return Transformation(fragments)
