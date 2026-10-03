from textual.theme import Theme

BG = "#1a1b26"
PANEL = "#16161e"
PANEL_HI = "#1f2335"

ACCENT = "#7aa2f7"
ACCENT2 = "#bb9af7"
CYAN = "#7dcfff"

FG = "#c0caf5"
FG_DIM = "#a9b1d6"
MUTED = "#565f89"

OK = "#9ece6a"
FAIL = "#f7768e"
WARN = "#e0af68"

BORDER = "#292e42"

USER = FG
REASON = FG_DIM

ACTION = ACCENT2
ACTION_BG = f"on {PANEL_HI}"
ACTION_FG = FG

OUT_FG = "#c8d3f5"
OUT_BG = f"on #20242f"

BORDER_FOCUS = ACCENT

THEME = Theme(
    name="sadhan",
    primary=ACCENT,
    secondary=ACCENT2,
    accent=ACCENT2,
    warning=WARN,
    error=FAIL,
    success=OK,
    foreground=FG,
    background=BG,
    surface=PANEL_HI,
    panel=PANEL,
    dark=True,
)