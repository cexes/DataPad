from textual.screen import Screen
from textual.widgets import Button, Static, Input, DataTable, TextArea
from textual.containers import Container, Vertical, Horizontal
from textual.app import ComposeResult
from textual.message import Message
from textual import work

from terminal_db.config import ConnectionProfile
from terminal_db.db_connection import DatabaseConnection
from terminal_db.query_executor import QueryExecutor, QueryResult


class QueryScreen(Screen):
    class Disconnected(Message):
        pass

    class DbConnected(Message):
        def __init__(self, version: str):
            super().__init__()
            self.version = version

    class ConnectionError(Message):
        def __init__(self, error: str):
            super().__init__()
            self.error = error

    class TablesLoaded(Message):
        def __init__(self, result: QueryResult):
            super().__init__()
            self.result = result

    class ColumnsLoaded(Message):
        def __init__(self, result: QueryResult):
            super().__init__()
            self.result = result

    class QueryResultReady(Message):
        def __init__(self, result: QueryResult):
            super().__init__()
            self.result = result

    DEFAULT_CSS = """
    QueryScreen {
        layout: vertical;
        height: 100%;
    }
    
    #header_bar {
        height: 3;
        background: $primary;
        padding: 0 2;
        align: left middle;
    }
    
    #connection_info {
        color: $text;
        text-style: bold;
    }
    
    #ssh_badge {
        color: $warning;
        margin-left: 2;
    }
    
    #disconnect_btn {
        dock: right;
    }
    
    #main_content {
        height: 1fr;
        layout: horizontal;
    }
    
    #sidebar {
        width: 35;
        border-right: solid $primary;
        padding: 0 1;
    }
    
    #sidebar_title {
        text-style: bold;
        color: $primary;
        padding: 1 0;
        border-bottom: solid $primary;
    }
    
    #tables_list {
        height: 1fr;
        border: solid $primary;
    }
    
    #query_area {
        width: 1fr;
        layout: vertical;
    }
    
    #query_input {
        height: 10;
        border: solid $primary;
    }
    
    #query_buttons {
        height: 3;
        padding: 0 1;
        align: left middle;
    }
    
    #execute_btn {
        margin-right: 1;
    }
    
    #results_table {
        height: 1fr;
        border: solid $primary;
    }
    
    #query_status {
        height: 3;
        padding: 0 1;
        background: $surface-darken-1;
        border-top: solid $primary;
    }
    
    #query_status.error {
        color: $error;
    }
    """

    def __init__(self, profile: ConnectionProfile):
        super().__init__()
        self.profile = profile
        self.db_conn: DatabaseConnection | None = None
        self.executor: QueryExecutor | None = None

    def compose(self) -> ComposeResult:
        with Horizontal(id="header_bar"):
            yield Static(f"Connected: {self.profile.db.host}:{self.profile.db.port}", id="connection_info")
            if self.profile.ssh.enabled:
                yield Static(f"[SSH: {self.profile.ssh.host}]", id="ssh_badge")
            yield Button("Disconnect", id="disconnect_btn", variant="error")

        with Horizontal(id="main_content"):
            with Vertical(id="sidebar"):
                yield Static("Tables", id="sidebar_title")
                yield DataTable(id="tables_list", cursor_type="row", zebra_stripes=True)

            with Vertical(id="query_area"):
                yield TextArea(id="query_input", language="sql", theme="monokai")
                with Horizontal(id="query_buttons"):
                    yield Button("Execute (Ctrl+Enter)", id="execute_btn", variant="success")
                    yield Button("Clear", id="clear_btn")
                yield DataTable(id="results_table", cursor_type="row", zebra_stripes=True)
                yield Static("", id="query_status")

    def on_mount(self) -> None:
        self._connect_to_db()

    @work(exclusive=True, thread=True)
    def _connect_to_db(self) -> None:
        try:
            self.db_conn = DatabaseConnection(self.profile.db, self.profile.ssh if self.profile.ssh.enabled else None)
            self.db_conn.connect()
            self.executor = QueryExecutor(self.db_conn)
            version = self.db_conn.get_server_version()
            self.post_message(self.DbConnected(version))
        except Exception as e:
            self.post_message(self.ConnectionError(str(e)))

    def on_db_connected(self, message: DbConnected) -> None:
        self.query_one("#connection_info", Static).update(
            f"Connected: {self.profile.db.host}:{self.profile.db.port} (Oracle {message.version})"
        )
        self._load_tables()

    def on_connection_error(self, message: ConnectionError) -> None:
        self.query_one("#query_status", Static).update(f"Connection failed: {message.error}")
        self.query_one("#query_status", Static).add_class("error")

    def _load_tables(self) -> None:
        self._fetch_tables()

    @work(exclusive=True, thread=True)
    def _fetch_tables(self) -> None:
        if not self.executor:
            return
        result = self.executor.get_tables()
        self.post_message(self.TablesLoaded(result))

    def on_tables_loaded(self, message: TablesLoaded) -> None:
        table = self.query_one("#tables_list", DataTable)
        table.clear()
        table.add_columns("Table Name")
        for row in message.result.rows:
            table.add_row(row[0])

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "execute_btn":
            self._execute_query()
        elif event.button.id == "clear_btn":
            self.query_one("#query_input", TextArea).text = ""
            self.query_one("#results_table", DataTable).clear()
            self.query_one("#query_status", Static).update("")
        elif event.button.id == "disconnect_btn":
            self._disconnect()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.data_table.id == "tables_list":
            row_data = event.cursor_row.value
            if row_data:
                self._show_table_structure(row_data)

    def _show_table_structure(self, table_name: str) -> None:
        self._fetch_columns(table_name)

    @work(exclusive=True, thread=True)
    def _fetch_columns(self, table_name: str) -> None:
        if not self.executor:
            return
        result = self.executor.get_table_columns(table_name)
        self.post_message(self.ColumnsLoaded(result))

    def on_columns_loaded(self, message: ColumnsLoaded) -> None:
        status = self.query_one("#query_status", Static)
        result = message.result
        if result.error:
            status.update(f"Error: {result.error}")
            status.add_class("error")
            return

        lines = ["Table structure:"]
        for row in result.rows:
            nullable = "NULL" if row[2] == "Y" else "NOT NULL"
            lines.append(f"  {row[0]}: {row[1]}({row[3]}) {nullable}")
        status.update("\n".join(lines))
        status.remove_class("error")

    def _execute_query(self) -> None:
        query = self.query_one("#query_input", TextArea).text.strip()
        if not query:
            return
        self._run_query(query)

    @work(exclusive=True, thread=True)
    def _run_query(self, query: str) -> None:
        if not self.executor:
            return
        result = self.executor.execute(query)
        self.post_message(self.QueryResultReady(result))

    def on_query_result_ready(self, message: QueryResultReady) -> None:
        table = self.query_one("#results_table", DataTable)
        status = self.query_one("#query_status", Static)
        table.clear()
        result = message.result

        if result.error:
            status.update(f"Error: {result.error}")
            status.add_class("error")
            return

        status.remove_class("error")

        if result.is_select:
            table.add_columns(*result.columns)
            for row in result.rows:
                formatted_row = [str(v) if v is not None else "NULL" for v in row]
                table.add_row(*formatted_row)
            status.update(f"{result.row_count} rows returned in {result.execution_time:.3f}s")
        else:
            status.update(f"Query executed. {result.rows_affected} rows affected in {result.execution_time:.3f}s")

    def _disconnect(self) -> None:
        if self.db_conn:
            self.db_conn.disconnect()
        self.post_message(self.Disconnected())

    def on_key(self, event) -> None:
        if event.key == "ctrl+enter" or event.key == "ctrl+j":
            event.prevent_default()
            self._execute_query()
