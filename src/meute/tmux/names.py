"""Names of the sessions, windows and options meute uses in tmux."""

MAIN_SESSION = "meute"  # session holding the window shown to the user
MAIN_WINDOW = "main"  # window of MAIN_SESSION holding the dashboard and the main area
MAIN_TARGET = f"={MAIN_SESSION}:{MAIN_WINDOW}"  # tmux target of the main window
BG_SESSION = "meute-bg"  # session holding the panes that are not displayed
ID_OPTION = "@meute_id"  # pane option: UUID of the meute session
ROLE_OPTION = "@meute_role"  # pane option: role of a layout pane
ROLE_BOARD = "board"  # role of the dashboard pane
ROLE_WELCOME = "welcome"  # role of the welcome pane
STATUS_OPTION = "@meute_status"  # global option shown on the right of the status bar
