# Datapad

Terminal-based database client for Oracle and PostgreSQL with SSH jump server support.

![Demo](demo.gif)

## Features

- **Multi-Database Support** - Connect to Oracle (service name/SID) or PostgreSQL
- **SSH Jump Server** - Tunnel connections through SSH jump servers with key-based or password authentication
- **Interactive SQL Prompt** - Full-featured terminal prompt with history and auto-completion
- **Table Formatting** - Results displayed as formatted tables in the terminal
- **Saved Connections** - SQLite database to save and load connection profiles
- **Meta Commands** - `.tables`, `.describe`, `.connect`, `.save`, `.load`, etc.

## Requirements

- Python 3.10+
- Oracle Instant Client (for `oracledb` thick mode, optional)

## Installation

```bash
cd terminal-db-client
pip install -e .
```

## Usage

```bash
tdb
```

## Commands

### Meta Commands (start with `.`)

| Command | Description |
|---------|-------------|
| `.connect` | Connect to a database (interactive prompt) |
| `.connect <name>` | Connect using a saved connection |
| `.disconnect` | Disconnect from database |
| `.tables` | List all tables in current schema |
| `.describe <table>` | Show table structure |
| `.save <name>` | Save current connection |
| `.load <name>` | Load a saved connection |
| `.list` | List all saved connections |
| `.delete <name>` | Delete a saved connection |
| `.clear` | Clear screen |
| `.exit` / `.quit` | Exit the application |
| `.help` | Show help |

### SQL Execution

Just type any SQL query and press Enter:

```sql
SELECT * FROM user_tables;
```

### Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Ctrl+R` | Search command history |
| `Tab` | Auto-completion |
| `Ctrl+C` | Cancel current input |
| `Ctrl+D` | Exit |

## Saved Connections

Connections are saved in `~/.terminal_db/connections.db` (SQLite).
Query history is saved in `~/.terminal_db/query_history.txt`.

## Connection Fields

### Database Connection
| Field | Description | Example |
|-------|-------------|---------|
| Database Type | `oracle` or `postgres` | `oracle` |
| Host | Database server hostname | `db.example.com` |
| Port | Database port | `1521` (Oracle) / `5432` (PostgreSQL) |
| Service Name | Oracle service name or PostgreSQL database name | `ORCLPDB1` / `mydb` |
| SID | Oracle SID (alternative to service name) | `ORCL` |
| Username | Database username | `system` |
| Password | Database password | `••••••` |

### SSH Jump Server (optional)
| Field | Description | Example |
|-------|-------------|---------|
| SSH Host | Jump server hostname | `jump.example.com` |
| SSH Port | SSH port (default: 22) | `22` |
| SSH Username | SSH username | `admin` |
| SSH Key Path | Path to SSH private key | `~/.ssh/id_rsa` |
| SSH Password | SSH password (if no key) | `••••••` |

## Architecture

```
src/terminal_db/
├── main.py                    # CLI entry point
├── config.py                  # Pydantic models for connection config
├── db_connection.py           # Base ABC + OracleConnection + factory
├── db_connection_postgres.py  # PostgreSQL connection
├── ssh_tunnel.py              # SSH tunnel manager with paramiko
├── query_executor.py          # SQL query executor (Oracle & PostgreSQL)
├── connection_store.py        # SQLite connection storage
└── ui/                        # Legacy TUI (deprecated)
```

## License

MIT
