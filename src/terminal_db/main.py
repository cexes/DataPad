import sys
import time
import logging
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.text import Text
from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.styles import Style

from terminal_db.config import ConnectionProfile, DbConfig, DbType, DB_DEFAULT_PORTS, SshConfig
from terminal_db.db_connection import create_connection
from terminal_db.query_executor import QueryExecutor
from terminal_db.connection_store import ConnectionStore

console = Console()
logger = logging.getLogger(__name__)

META_COMMANDS = [
    ".help", ".connect", ".disconnect", ".tables", ".describe",
    ".save", ".load", ".list", ".delete", ".exit", ".quit", ".clear",
]

SQL_KEYWORDS = [
    "SELECT", "FROM", "WHERE", "INSERT", "UPDATE", "DELETE", "CREATE",
    "DROP", "ALTER", "JOIN", "LEFT", "RIGHT", "INNER", "OUTER", "ON",
    "GROUP", "BY", "ORDER", "HAVING", "LIMIT", "OFFSET", "UNION",
    "AS", "AND", "OR", "NOT", "IN", "IS", "NULL", "LIKE", "BETWEEN",
    "EXISTS", "CASE", "WHEN", "THEN", "ELSE", "END", "DISTINCT",
    "COUNT", "SUM", "AVG", "MIN", "MAX", "INTO", "VALUES", "SET",
]


class TerminalDbCLI:
    def __init__(self):
        self.store = ConnectionStore()
        self.db_conn: Optional[DatabaseConnection] = None
        self.executor: Optional[QueryExecutor] = None
        self.profile: Optional[ConnectionProfile] = None
        self.history_file = Path.home() / ".terminal_db" / "query_history.txt"
        self.history_file.parent.mkdir(parents=True, exist_ok=True)
        
        self.style = Style.from_dict({
            "prompt": "ansicyan bold",
            "connected": "ansigreen bold",
            "disconnected": "ansired",
            "error": "ansired bold",
            "success": "ansigreen",
            "info": "ansiblue",
            "warning": "ansiyellow",
        })
        
        self.session = PromptSession(
            history=FileHistory(str(self.history_file)),
            auto_suggest=AutoSuggestFromHistory(),
            completer=WordCompleter(META_COMMANDS + SQL_KEYWORDS, ignore_case=True),
            style=self.style,
        )

    def run(self) -> None:
        self._print_banner()
        
        query_buffer = []
        
        while True:
            try:
                if query_buffer:
                    prompt_text = "...> "
                else:
                    prompt_text = self._get_prompt()
                
                user_input = self.session.prompt(prompt_text).strip()
                
                if not user_input:
                    continue
                
                if user_input.startswith("."):
                    if query_buffer:
                        console.print("[yellow]Discarding incomplete query[/yellow]")
                        query_buffer = []
                    self._handle_meta_command(user_input)
                    continue
                
                query_buffer.append(user_input)
                combined = " ".join(query_buffer)
                
                if combined.endswith(";"):
                    self._execute_sql(combined)
                    query_buffer = []
                    
            except KeyboardInterrupt:
                if query_buffer:
                    console.print("\n[yellow]Query cancelled[/yellow]")
                    query_buffer = []
                console.print()
                continue
            except EOFError:
                self._disconnect()
                console.print("\nGoodbye!")
                break
            except Exception as e:
                console.print(f"[red]Error: {e}[/red]")

    def _print_banner(self) -> None:
        banner = Text()
        banner.append("Terminal DB Client", style="bold cyan")
        banner.append(" - Oracle Database CLI\n", style="cyan")
        banner.append("Type ", style="dim")
        banner.append(".help", style="bold green")
        banner.append(" for available commands\n", style="dim")
        console.print(Panel(banner, border_style="cyan"))

    def _get_prompt(self) -> str:
        if self.db_conn and self.db_conn.is_connected:
            host = self.profile.db.host if self.profile else "unknown"
            ssh = " [SSH]" if self.profile and self.profile.ssh.enabled else ""
            return f"[{host}{ssh}] SQL> "
        return "SQL> "

    def _handle_meta_command(self, command: str) -> None:
        parts = command.split(maxsplit=1)
        cmd = parts[0].lower()
        args = parts[1].strip() if len(parts) > 1 else ""

        commands = {
            ".help": self._cmd_help,
            ".connect": lambda: self._cmd_connect(args),
            ".disconnect": self._cmd_disconnect,
            ".tables": self._cmd_tables,
            ".describe": lambda: self._cmd_describe(args),
            ".save": lambda: self._cmd_save(args),
            ".load": lambda: self._cmd_load(args),
            ".list": self._cmd_list,
            ".delete": lambda: self._cmd_delete(args),
            ".exit": self._cmd_exit,
            ".quit": self._cmd_exit,
            ".clear": lambda: console.clear(),
        }

        handler = commands.get(cmd)
        if handler:
            if callable(handler):
                if args or cmd in [".describe", ".save", ".load", ".delete", ".connect"]:
                    handler()
                else:
                    handler()
            else:
                handler()
        else:
            console.print(f"[red]Unknown command: {cmd}[/red]")
            console.print("Type [green].help[/green] for available commands")

    def _cmd_help(self) -> None:
        help_text = """
[bold cyan]Meta Commands:[/bold cyan]
  [green].connect[/green]        Connect to a database
  [green].disconnect[/green]     Disconnect from database
  [green].tables[/green]         List all tables in current schema
  [green].describe <table>[/green]  Show table structure
  [green].save <name>[/green]    Save current connection
  [green].load <name>[/green]    Load a saved connection
  [green].list[/green]           List all saved connections
  [green].delete <name>[/green]  Delete a saved connection
  [green].clear[/green]          Clear screen
  [green].exit / .quit[/green]   Exit the application

[bold cyan]Tips:[/bold cyan]
  - End query with [yellow];[/yellow] to execute (Enter to continue typing)
  - Use [yellow]Ctrl+R[/yellow] to search command history
  - Use [yellow]Tab[/yellow] for auto-completion
  - Results are paginated automatically
"""
        console.print(Panel(help_text, title="Help", border_style="cyan"))

    def _cmd_connect(self, name: str = "") -> None:
        if self.db_conn and self.db_conn.is_connected:
            console.print("[yellow]Already connected. Use .disconnect first.[/yellow]")
            return

        if name:
            profile = self.store.load(name)
            if profile is None:
                console.print(f"[red]Connection '{name}' not found[/red]")
                return
            self.profile = profile
        else:
            self.profile = self._prompt_connection()

        if self.profile is None:
            return

        console.print(f"[cyan]Connecting to {self.profile.db.host}:{self.profile.db.port}...[/cyan]")
        
        if self.profile.ssh.enabled:
            console.print(f"[cyan]SSH tunnel via {self.profile.ssh.host}...[/cyan]")

        try:
            self.db_conn = create_connection(
                self.profile.db,
                self.profile.ssh if self.profile.ssh.enabled else None,
            )
            self.db_conn.connect()
            self.executor = QueryExecutor(self.db_conn)
            
            version = self.db_conn.get_server_version()
            db_label = self.db_conn.db_type.value.upper()
            console.print(f"[green]Connected to {db_label} {version}[/green]")
            
            if not name:
                try:
                    self.store.save(self.profile)
                    console.print(f"[green]Connection saved as '{self.profile.name}'[/green]")
                except Exception as e:
                    console.print(f"[yellow]Warning: Could not save connection: {e}[/yellow]")
            
        except Exception as e:
            console.print(f"[red]Connection failed: {e}[/red]")
            self.db_conn = None
            self.executor = None
            self.profile = None

    def _prompt_connection(self) -> Optional[ConnectionProfile]:
        console.print("\n[bold cyan]Database Connection[/bold cyan]")

        db_type_str = Prompt.ask("Database type", default="oracle", choices=["oracle", "postgres"])
        db_type = DbType(db_type_str)
        default_port = str(DB_DEFAULT_PORTS[db_type])

        host = Prompt.ask("Host", default="")
        if not host:
            return None

        port = Prompt.ask("Port", default=default_port)
        service_name = Prompt.ask("Database/Service Name", default="")
        username = Prompt.ask("Username", default="")
        password = Prompt.ask("Password", password=True, default="")

        sid = None
        mode = "NORMAL"
        if db_type == DbType.ORACLE:
            sid = Prompt.ask("SID (optional)", default="") or None
            mode = Prompt.ask("Mode", default="NORMAL", choices=["NORMAL", "SYSDBA", "SYSOPER"])

        console.print("\n[bold cyan]SSH Jump Server (optional, leave empty to skip)[/bold cyan]")
        ssh_host = Prompt.ask("SSH Host", default="")
        
        ssh_config = SshConfig()
        if ssh_host:
            ssh_config.enabled = True
            ssh_config.host = ssh_host
            ssh_config.port = int(Prompt.ask("SSH Port", default="22"))
            ssh_config.username = Prompt.ask("SSH Username", default="")
            ssh_config.key_path = Prompt.ask("SSH Key Path", default="") or None
            ssh_config.password = Prompt.ask("SSH Password", password=True, default="") or None

        name = Prompt.ask("Connection name (auto-saved)", default=f"{host}:{port}")

        db_config = DbConfig(
            db_type=db_type,
            host=host,
            port=int(port),
            service_name=service_name,
            sid=sid,
            username=username,
            password=password,
            mode=mode,
        )

        return ConnectionProfile(name=name, db=db_config, ssh=ssh_config)

    def _cmd_disconnect(self) -> None:
        self._disconnect()
        console.print("[green]Disconnected[/green]")

    def _disconnect(self) -> None:
        if self.db_conn:
            try:
                self.db_conn.disconnect()
            except Exception:
                pass
        self.db_conn = None
        self.executor = None
        self.profile = None

    def _cmd_tables(self) -> None:
        if not self._check_connection():
            return

        result = self.executor.get_tables()
        if result.error:
            console.print(f"[red]Error: {result.error}[/red]")
            return

        if not result.rows:
            console.print("[yellow]No tables found[/yellow]")
            return

        table = Table(title="Tables", border_style="cyan")
        table.add_column("#", style="dim")
        table.add_column("Table Name", style="green")
        
        for i, row in enumerate(result.rows, 1):
            table.add_row(str(i), row[0])
        
        console.print(table)
        console.print(f"[dim]{result.row_count} tables[/dim]")

    def _cmd_describe(self, table_name: str) -> None:
        if not self._check_connection():
            return

        if not table_name:
            console.print("[red]Usage: .describe <table_name>[/red]")
            return

        result = self.executor.get_table_columns(table_name.upper())
        if result.error:
            console.print(f"[red]Error: {result.error}[/red]")
            return

        if not result.rows:
            console.print(f"[yellow]Table '{table_name}' not found[/yellow]")
            return

        table = Table(title=f"Columns in {table_name.upper()}", border_style="cyan")
        table.add_column("Column Name", style="green")
        table.add_column("Data Type", style="yellow")
        table.add_column("Nullable", style="dim")
        table.add_column("Length", style="dim")
        
        for row in result.rows:
            nullable = "YES" if row[2] == "Y" else "NO"
            table.add_row(row[0], row[1], nullable, str(row[3]))
        
        console.print(table)

    def _cmd_save(self, name: str) -> None:
        if not self.profile:
            console.print("[red]No active connection to save[/red]")
            return

        if name:
            self.profile.name = name
        
        try:
            self.store.save(self.profile)
            console.print(f"[green]Connection '{self.profile.name}' saved[/green]")
        except Exception as e:
            console.print(f"[red]Error saving: {e}[/red]")

    def _cmd_load(self, name: str) -> None:
        if not name:
            console.print("[red]Usage: .load <connection_name>[/red]")
            return
        
        self._cmd_connect(name)

    def _cmd_list(self) -> None:
        connections = self.store.list_all()
        
        if not connections:
            console.print("[yellow]No saved connections[/yellow]")
            return

        table = Table(title="Saved Connections", border_style="cyan")
        table.add_column("#", style="dim")
        table.add_column("Name", style="green")
        table.add_column("Host", style="yellow")
        table.add_column("Port", style="dim")
        table.add_column("SSH", style="dim")
        
        for i, conn in enumerate(connections, 1):
            ssh = "Yes" if conn["ssh_enabled"] else "No"
            table.add_row(str(i), conn["name"], conn["db_host"], str(conn["db_port"]), ssh)
        
        console.print(table)

    def _cmd_delete(self, name: str) -> None:
        if not name:
            console.print("[red]Usage: .delete <connection_name>[/red]")
            return
        
        if Confirm.ask(f"Delete connection '{name}'?"):
            if self.store.delete(name):
                console.print(f"[green]Connection '{name}' deleted[/green]")
            else:
                console.print(f"[red]Connection '{name}' not found[/red]")

    def _cmd_exit(self) -> None:
        self._disconnect()
        console.print("\n[green]Goodbye![/green]")
        sys.exit(0)

    def _execute_sql(self, query: str) -> None:
        if not self._check_connection():
            return

        query = query.strip()
        if query.endswith(";"):
            query = query[:-1].strip()
        if not query:
            return

        start_time = time.time()
        
        try:
            result = self.executor.execute(query)
            execution_time = time.time() - start_time

            if result.error:
                console.print(f"[red]Error: {result.error}[/red]")
                return

            if result.is_select:
                self._display_results(result, execution_time)
            else:
                console.print(f"[green]Query executed successfully. {result.rows_affected} rows affected in {execution_time:.3f}s[/green]")
                
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")

    def _display_results(self, result, execution_time: float) -> None:
        if not result.rows:
            console.print("[yellow]No rows returned[/yellow]")
            console.print(f"[dim]Execution time: {execution_time:.3f}s[/dim]")
            return

        table = Table(border_style="cyan")
        
        for col in result.columns:
            table.add_column(str(col), style="green")
        
        for row in result.rows:
            formatted_row = [str(v) if v is not None else "[dim]NULL[/dim]" for v in row]
            table.add_row(*formatted_row)
        
        console.print(table)
        console.print(f"[dim]{result.row_count} rows returned in {execution_time:.3f}s[/dim]")

    def _check_connection(self) -> bool:
        if not self.db_conn or not self.db_conn.is_connected:
            console.print("[red]Not connected. Use .connect first.[/red]")
            return False
        return True


def main():
    logging.basicConfig(level=logging.INFO)
    cli = TerminalDbCLI()
    cli.run()


if __name__ == "__main__":
    main()
