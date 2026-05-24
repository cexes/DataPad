import logging
from mcp.server.fastmcp import FastMCP

from terminal_db.config import DbType
from terminal_db.db_connection import create_connection
from terminal_db.query_executor import QueryExecutor
from terminal_db.connection_store import ConnectionStore
from terminal_db.mcp.mcp_config import McpConfig, parse_args

logger = logging.getLogger(__name__)

store = ConnectionStore()
_db_conn = None
_executor = None


def _ensure_connected() -> str | None:
    global _db_conn, _executor
    if _db_conn is None or not _db_conn.is_connected:
        return "No active connection. Use connect() first."
    return None


def main():
    logging.basicConfig(level=logging.WARNING)

    cfg = McpConfig()
    cfg.load_toml()
    cfg.apply_cli_args(parse_args())

    mcp = FastMCP("DataPad")

    if "list_connections" in cfg.allowed_tools:
        @mcp.tool()
        def list_connections() -> list[dict]:
            """List all saved database connections."""
            return store.list_all()

    if "connect" in cfg.allowed_tools:
        @mcp.tool()
        def connect(connection_name: str) -> str:
            """Connect to a database using a saved connection profile."""
            global _db_conn, _executor

            profile = store.load(connection_name)
            if profile is None:
                return f"Connection '{connection_name}' not found"

            try:
                _db_conn = create_connection(
                    profile.db,
                    profile.ssh if profile.ssh.enabled else None,
                )
                _db_conn.connect()
                _executor = QueryExecutor(_db_conn, max_rows=cfg.max_rows)
                version = _db_conn.get_server_version()
                return f"Connected to {profile.db.db_type.value.upper()} {version} as {profile.db.username}@{profile.db.host}"
            except Exception as e:
                _db_conn = None
                _executor = None
                return f"Connection failed: {e}"

    if "list_tables" in cfg.allowed_tools:
        @mcp.tool()
        def list_tables() -> list[str]:
            """List all tables in the current database schema."""
            global _executor
            error = _ensure_connected()
            if error:
                raise RuntimeError(error)
            result = _executor.get_tables()
            if result.error:
                raise RuntimeError(result.error)
            return [row[0] for row in result.rows]

    if "describe_table" in cfg.allowed_tools:
        @mcp.tool()
        def describe_table(table_name: str) -> list[dict]:
            """Show column structure of a table.

            Args:
                table_name: Name of the table to describe
            """
            global _executor
            error = _ensure_connected()
            if error:
                raise RuntimeError(error)
            lookup = table_name.upper() if _db_conn.db_type == DbType.ORACLE else table_name.lower()
            result = _executor.get_table_columns(lookup)
            if result.error:
                raise RuntimeError(result.error)
            if not result.rows:
                return []
            return [dict(zip(result.columns, row)) for row in result.rows]

    if "execute_query" in cfg.allowed_tools:
        @mcp.tool()
        def execute_query(query: str) -> str:
            """Execute a SQL query and return results as formatted text.

            Args:
                query: SQL query to execute
            """
            global _executor
            error = _ensure_connected()
            if error:
                raise RuntimeError(error)

            query = query.strip().rstrip(";")
            if cfg.query_mode == "read-only" and not query.upper().lstrip().startswith("SELECT"):
                raise RuntimeError("Only SELECT queries are allowed (read-only mode)")

            result = _executor.execute(query)
            if result.error:
                raise RuntimeError(result.error)

            if not result.columns:
                return "Query executed successfully"

            header = " | ".join(str(c) for c in result.columns)
            sep = "-+-".join("-" * len(str(c)) for c in result.columns)
            lines = [header, sep]
            for row in result.rows:
                lines.append(" | ".join(str(v) if v is not None else "NULL" for v in row))
            lines.append(f"\n{result.row_count} rows in {result.execution_time:.3f}s")
            return "\n".join(lines)

    mcp.run()


if __name__ == "__main__":
    main()
