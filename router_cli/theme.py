"""Minimal near-black theme with subtle blue accents."""

from prompt_toolkit.styles import Style

FOCUSED_BUTTON = "bg:#82aaff #09111f bold nounderline noreverse"

MENU_STYLE = Style.from_dict(
    {
        "": "bg:#090909 #c7cbd3",
        "header": "bg:#090909 #adb4bf",
        "brand-icon": "#82aaff bold",
        "title": "#82aaff bold",
        "column": "bg:#101010 #858c99 bold",
        "action-menu cursor-line": "bg:#82aaff #09111f bold noreverse nounderline",
        "muted": "#737b89",
        "good": "#8ab59c",
        "warning": "#d4b46d",
        "error": "#da858b",
        "separator": "#292e35",
        "footer": "bg:#090909 #858c99",
        "activity": "bg:#090909 #a4acb8",
        "dialog": "bg:#101010 #c7cbd3 noreverse",
        "dialog.body": "bg:#101010 #c7cbd3 noreverse",
        "dialog.body label": "bg:#101010 #c7cbd3 noreverse",
        "dialog.body text-area last-line": "nounderline",
        "dialog shadow": "bg:#050607 #050607",
        "input-field": "bg:#141414 #aeb6c2 noreverse",
        "input-field.focused": "bg:#1c2026 #ffffff noreverse",
        "input-cursor": "bg:#90c7ff #0b1119 bold noreverse",
        "input-field selection": "bg:#344555 #ffffff noreverse",
        "dialog frame.label": "#82aaff bold",
        "dialog frame.border": "#2c3139",
        "button": "bg:#203858 #bcd4ff noreverse",
        "button.focused": FOCUSED_BUTTON,
        "button.focused button.text": FOCUSED_BUTTON,
        "button.focused button.arrow": FOCUSED_BUTTON,
        "text-area": "bg:#141414 #c7cbd3",
        "text-area focused": "bg:#1c2026 #ffffff",
        "section": "bg:#090909 #c7cbd3",
        "section frame.border": "#292e35",
        "section frame.label": "#737b89",
        "hotkey": "bg:#1c2026 #e6e9ef bold noreverse",
        "scrollbar.background": "bg:#101010",
        "scrollbar.button": "bg:#38404c",
    }
)
