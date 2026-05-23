import logging
from typing import Optional
import psycopg
from terminal_db.config import DbConfig, DbType, SshConfig
from terminal_db.db_connection import DatabaseConnection

logger = logging.getLogger(__name__)


class PostgresConnection(DatabaseConnection):
    def connect(self) -> None:
        host, port = self._setup_ssh_tunnel(self.db_config.host, self.db_config.port)
        conn_str = self._build_conn_str(host, port)

        logger.info(f"Connecting to PostgreSQL at {host}:{port}")
        self._connection = psycopg.connect(conn_str)
        self._connected = True
        logger.info("PostgreSQL connection established")

    def _build_conn_str(self, host: str, port: int) -> str:
        dbname = self.db_config.service_name or "postgres"
        return (
            f"host={host} port={port} "
            f"dbname={dbname} "
            f"user={self.db_config.username} "
            f"password={self.db_config.password}"
        )

    @property
    def connection(self) -> psycopg.Connection:
        if self._connection is None:
            raise RuntimeError("Not connected to database")
        return self._connection

    def get_server_version(self) -> str:
        if self._connection is None:
            return "Not connected"
        try:
            return self._connection.execute("SELECT version()").scalar()
        except Exception:
            return "Unknown"

    @property
    def db_type(self) -> DbType:
        return DbType.POSTGRES
