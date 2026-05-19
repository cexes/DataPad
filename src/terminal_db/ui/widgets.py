from textual.widgets import Input, Label, Static
from textual.containers import Vertical, ScrollableContainer
from textual.app import ComposeResult


class ConnectionForm(ScrollableContainer):
    def compose(self) -> ComposeResult:
        yield Static("Database Connection", classes="section-title")
        yield Label("Host")
        yield Input(placeholder="db.example.com", id="db_host")
        yield Label("Port")
        yield Input(placeholder="1521", id="db_port", value="1521")
        yield Label("Service Name")
        yield Input(placeholder="ORCL", id="db_service")
        yield Label("SID (optional)")
        yield Input(placeholder="ORCL", id="db_sid")
        yield Label("Username")
        yield Input(placeholder="system", id="db_user")
        yield Label("Password")
        yield Input(placeholder="password", id="db_pass", password=True)

    def get_values(self) -> dict:
        return {
            "host": self.query_one("#db_host", Input).value,
            "port": int(self.query_one("#db_port", Input).value or "1521"),
            "service_name": self.query_one("#db_service", Input).value,
            "sid": self.query_one("#db_sid", Input).value or None,
            "username": self.query_one("#db_user", Input).value,
            "password": self.query_one("#db_pass", Input).value,
        }


class SshForm(ScrollableContainer):
    def compose(self) -> ComposeResult:
        yield Static("SSH Jump Server", classes="section-title")
        yield Label("SSH Host")
        yield Input(placeholder="jump.example.com", id="ssh_host")
        yield Label("SSH Port")
        yield Input(placeholder="22", id="ssh_port", value="22")
        yield Label("SSH Username")
        yield Input(placeholder="admin", id="ssh_user")
        yield Label("SSH Key Path")
        yield Input(placeholder="~/.ssh/id_rsa", id="ssh_key")
        yield Label("SSH Password (optional)")
        yield Input(placeholder="", id="ssh_pass", password=True)

    def get_values(self) -> dict:
        return {
            "enabled": bool(self.query_one("#ssh_host", Input).value),
            "host": self.query_one("#ssh_host", Input).value,
            "port": int(self.query_one("#ssh_port", Input).value or "22"),
            "username": self.query_one("#ssh_user", Input).value,
            "key_path": self.query_one("#ssh_key", Input).value or None,
            "password": self.query_one("#ssh_pass", Input).value or None,
        }
