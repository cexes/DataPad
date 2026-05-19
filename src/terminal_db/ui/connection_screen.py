from textual.screen import Screen
from textual.widgets import Button, Static, Input, DataTable
from textual.containers import Container, Vertical, Horizontal
from textual.app import ComposeResult
from textual.message import Message

from terminal_db.config import ConnectionProfile, DbConfig, SshConfig
from terminal_db.ui.widgets import ConnectionForm, SshForm
from terminal_db.connection_store import ConnectionStore


class ConnectionScreen(Screen):
    class Connected(Message):
        def __init__(self, profile: ConnectionProfile):
            super().__init__()
            self.profile = profile

    DEFAULT_CSS = """
    ConnectionScreen {
        layout: vertical;
        height: 100%;
    }
    
    #title_bar {
        height: 3;
        background: $primary;
        padding: 0 2;
        align: center middle;
    }
    
    #title {
        color: $text;
        text-style: bold;
    }
    
    #main_layout {
        height: 1fr;
        layout: horizontal;
    }
    
    #saved_connections_panel {
        width: 40;
        border-right: solid $primary;
        padding: 1;
    }
    
    #saved_title {
        text-style: bold;
        color: $primary;
        padding-bottom: 1;
        border-bottom: solid $primary;
    }
    
    #saved_connections_list {
        height: 1fr;
        border: solid $primary;
        margin-top: 1;
    }
    
    #connection_form_panel {
        width: 1fr;
        padding: 1;
        layout: vertical;
    }
    
    #forms_container {
        height: 1fr;
        layout: horizontal;
    }
    
    .form_panel {
        width: 1fr;
        border: solid $primary;
        padding: 1;
        margin: 0 1;
    }
    
    .section-title {
        text-style: bold;
        color: $primary;
        padding: 1 0;
        border-bottom: solid $primary;
    }
    
    #button_row {
        height: 4;
        padding: 1 2;
        align: center middle;
    }
    
    #status_message {
        height: 3;
        padding: 0 2;
        text-align: center;
    }
    
    #status_message.error {
        color: $error;
    }
    """

    def __init__(self):
        super().__init__()
        self.store = ConnectionStore()

    def compose(self) -> ComposeResult:
        with Horizontal(id="title_bar"):
            yield Static("Terminal DB Client - Oracle", id="title")

        with Horizontal(id="main_layout"):
            with Vertical(id="saved_connections_panel"):
                yield Static("Saved Connections", id="saved_title")
                yield DataTable(id="saved_connections_list", cursor_type="row", zebra_stripes=True)
                with Horizontal():
                    yield Button("Load", id="load_connection", variant="primary")
                    yield Button("Delete", id="delete_connection", variant="error")

            with Vertical(id="connection_form_panel"):
                yield Static("New Connection", classes="section-title")
                yield Input(placeholder="Connection name (e.g., Production DB)", id="connection_name")
                with Horizontal(id="forms_container"):
                    with Container(classes="form-panel"):
                        yield ConnectionForm()
                    with Container(classes="form-panel"):
                        yield SshForm()

        with Horizontal(id="button_row"):
            yield Button("Connect", id="connect", variant="success")
            yield Button("Save Connection", id="save", variant="primary")
            yield Button("Exit", id="exit", variant="error")

        yield Static("", id="status_message")

    def on_mount(self) -> None:
        self._load_saved_connections()

    def _load_saved_connections(self) -> None:
        table = self.query_one("#saved_connections_list", DataTable)
        table.clear()
        table.add_columns("Name", "Host", "Port", "SSH")
        
        connections = self.store.list_all()
        for conn in connections:
            ssh = "Yes" if conn["ssh_enabled"] else "No"
            table.add_row(conn["name"], conn["db_host"], str(conn["db_port"]), ssh)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "connect":
            self._attempt_connect()
        elif event.button.id == "save":
            self._save_connection()
        elif event.button.id == "load_connection":
            self._load_connection()
        elif event.button.id == "delete_connection":
            self._delete_connection()
        elif event.button.id == "exit":
            self.app.exit()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.data_table.id == "saved_connections_list":
            self._load_connection()

    def _attempt_connect(self) -> None:
        conn_form = self.query_one(ConnectionForm)
        ssh_form = self.query_one(SshForm)
        status = self.query_one("#status_message", Static)

        db_values = conn_form.get_values()
        ssh_values = ssh_form.get_values()

        if not db_values["host"]:
            status.update("Error: Database host is required")
            status.add_class("error")
            return

        if not db_values["username"]:
            status.update("Error: Username is required")
            status.add_class("error")
            return

        if not db_values["password"]:
            status.update("Error: Password is required")
            status.add_class("error")
            return

        if not db_values["service_name"] and not db_values["sid"]:
            status.update("Error: Service Name or SID is required")
            status.add_class("error")
            return

        name = self.query_one("#connection_name", Input).value or f"{db_values['host']}:{db_values['port']}"
        
        db_config = DbConfig(**db_values)
        ssh_config = SshConfig(**ssh_values)
        profile = ConnectionProfile(name=name, db=db_config, ssh=ssh_config)

        status.update("Connecting...")
        status.remove_class("error")
        self.post_message(self.Connected(profile))

    def _save_connection(self) -> None:
        conn_form = self.query_one(ConnectionForm)
        ssh_form = self.query_one(SshForm)
        status = self.query_one("#status_message", Static)
        name_input = self.query_one("#connection_name", Input)

        name = name_input.value.strip()
        if not name:
            status.update("Error: Connection name is required to save")
            status.add_class("error")
            return

        db_values = conn_form.get_values()
        ssh_values = ssh_form.get_values()

        if not db_values["host"] or not db_values["username"] or not db_values["password"]:
            status.update("Error: Fill required fields before saving")
            status.add_class("error")
            return

        db_config = DbConfig(**db_values)
        ssh_config = SshConfig(**ssh_values)
        profile = ConnectionProfile(name=name, db=db_config, ssh=ssh_config)

        try:
            self.store.save(profile)
            self._load_saved_connections()
            status.update(f"Connection '{name}' saved successfully")
            status.remove_class("error")
        except Exception as e:
            status.update(f"Error saving: {str(e)}")
            status.add_class("error")

    def _load_connection(self) -> None:
        table = self.query_one("#saved_connections_list", DataTable)
        status = self.query_one("#status_message", Static)
        
        if not table.cursor_row:
            status.update("Select a connection to load")
            status.add_class("error")
            return

        row_data = table.get_row_at(table.cursor_coordinate.row)
        if not row_data:
            return

        name = row_data[0]
        profile = self.store.load(name)
        
        if profile is None:
            status.update(f"Connection '{name}' not found")
            status.add_class("error")
            return

        self.query_one("#connection_name", Input).value = profile.name
        self.query_one("#db_host", Input).value = profile.db.host
        self.query_one("#db_port", Input).value = str(profile.db.port)
        self.query_one("#db_service", Input).value = profile.db.service_name
        self.query_one("#db_sid", Input).value = profile.db.sid or ""
        self.query_one("#db_user", Input).value = profile.db.username
        self.query_one("#db_pass", Input).value = profile.db.password
        self.query_one("#ssh_host", Input).value = profile.ssh.host
        self.query_one("#ssh_port", Input).value = str(profile.ssh.port)
        self.query_one("#ssh_user", Input).value = profile.ssh.username
        self.query_one("#ssh_key", Input).value = profile.ssh.key_path or ""
        self.query_one("#ssh_pass", Input).value = profile.ssh.password or ""

        status.update(f"Loaded connection '{name}'")
        status.remove_class("error")

    def _delete_connection(self) -> None:
        table = self.query_one("#saved_connections_list", DataTable)
        status = self.query_one("#status_message", Static)
        
        if not table.cursor_row:
            status.update("Select a connection to delete")
            status.add_class("error")
            return

        row_data = table.get_row_at(table.cursor_coordinate.row)
        if not row_data:
            return

        name = row_data[0]
        
        if self.store.delete(name):
            self._load_saved_connections()
            status.update(f"Connection '{name}' deleted")
            status.remove_class("error")
        else:
            status.update(f"Failed to delete '{name}'")
            status.add_class("error")
