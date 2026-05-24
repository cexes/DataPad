import argparse;
from pathlib import Path;
from typing import Optional;
try:
    import tomllib
except ImportError:
    import tomli as tomllib;

ALL_TOOLS = [
    "list_tables", "describe_table",
    "execute_query","connect",
    "list_connections"
];

class McpConfig:
    def __init__(self) -> None:
        self.allowed_tools: list[str] = ALL_TOOLS;
        self.query_mode: str = "read-only";
        self.max_rows: int = 200

    def load_toml(self) -> None:
        path = Path.home() / ".terminal_db" / "mcp.toml"
        if not path.exists():
            return
        with open(path, "rb") as f:
            data = tomllib.load(f)
        if "tools" in data:
            self.allowed_tools = data["tools"].get("allowed", self.allowed_tools)
        if "query" in data:
            self.query_mode = data["query"].get("mode", self.query_mode)
            self.max_rows = data["query"].get("max_rows", self.max_rows)

    def apply_cli_args(self, args: "argparse.Namespace") -> None:
        if args.allow_write:
            self.query_mode = "write"
        if args.max_rows is not None:
            self.max_rows = args.max_rows
        if args.tools is not None:
            self.allowed_tools = [t.strip() for t in args.tools.split(",")]


def parse_args() -> "argparse.Namespace":
    parser = argparse.ArgumentParser(prog="tdb-mcp")
    parser.add_argument("--allow-write", action="store_true", help="Allow write queries")
    parser.add_argument("--max-rows", type=int, help="Max rows returned per query")
    parser.add_argument("--tools", type=str, help="Comma-separated list of allowed tools")
    return parser.parse_args()
