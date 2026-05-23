import logging
from abc import ABC, abstractmethod
from typing import Optional, Any
import oracledb
from terminal_db.config import DbConfig, DbType, SshConfig
from terminal_db.ssh_tunnel import SshTunnel

logger = logging.getLogger(__name__)


class DatabaseConnection(ABC):
    def __init__(self, db_config: DbConfig, ssh_config: Optional[SshConfig] = None):
        self.db_config = db_config
        self.ssh_config = ssh_config
        self._ssh_tunnel: Optional[SshTunnel] = None
        self._connection: Optional[Any] = None
        self._connected = False

    def _setup_ssh_tunnel(self, host: str, port: int) -> tuple[str, int]:
        if self.ssh_config and self.ssh_config.enabled:
            self._ssh_tunnel = SshTunnel(
                config=self.ssh_config,
                remote_host=host,
                remote_port=port,
            )
            local_port = self._ssh_tunnel.start()
            return "127.0.0.1", local_port
        return host, port

    @abstractmethod
    def connect(self) -> None:
        pass

    @property
    @abstractmethod
    def connection(self) -> Any:
        pass

    @property
    def is_connected(self) -> bool:
        return self._connected and self._connection is not None

    def disconnect(self) -> None:
        if self._connection:
            try:
                self._connection.close()
            except Exception as e:
                logger.error(f"Error closing connection: {e}")
            self._connection = None

        if self._ssh_tunnel:
            try:
                self._ssh_tunnel.stop()
            except Exception as e:
                logger.error(f"Error closing SSH tunnel: {e}")
            self._ssh_tunnel = None

        self._connected = False
        logger.info("Disconnected from database")

    @abstractmethod
    def get_server_version(self) -> str:
        pass

    @property
    @abstractmethod
    def db_type(self) -> DbType:
        pass


class OracleConnection(DatabaseConnection):
    MODE_MAP = {
        "NORMAL": oracledb.AUTH_MODE_DEFAULT,
        "SYSDBA": oracledb.AUTH_MODE_SYSDBA,
        "SYSOPER": oracledb.AUTH_MODE_SYSOPER,
    }

    def connect(self) -> None:
        host, port = self._setup_ssh_tunnel(self.db_config.host, self.db_config.port)
        dsn = self._build_dsn(host, port)
        mode = self.MODE_MAP.get(self.db_config.mode, oracledb.AUTH_MODE_DEFAULT)

        logger.info(f"Connecting to Oracle at {dsn}")
        self._connection = oracledb.connect(
            user=self.db_config.username,
            password=self.db_config.password,
            dsn=dsn,
            mode=mode,
        )
        self._connected = True
        logger.info("Oracle connection established")

    def _build_dsn(self, host: str, port: int) -> str:
        if self.db_config.service_name:
            return oracledb.makedsn(host, port, service_name=self.db_config.service_name)
        elif self.db_config.sid:
            return oracledb.makedsn(host, port, sid=self.db_config.sid)
        return f"{host}:{port}"

    @property
    def connection(self) -> oracledb.Connection:
        if self._connection is None:
            raise RuntimeError("Not connected to database")
        return self._connection

    def get_server_version(self) -> str:
        if self._connection is None:
            return "Not connected"
        try:
            return self._connection.version
        except Exception:
            return "Unknown"

    @property
    def db_type(self) -> DbType:
        return DbType.ORACLE


def create_connection(db_config: DbConfig, ssh_config: Optional[SshConfig] = None) -> DatabaseConnection:
    if db_config.db_type == DbType.ORACLE:
        return OracleConnection(db_config, ssh_config)
    elif db_config.db_type == DbType.POSTGRES:
        from terminal_db.db_connection_postgres import PostgresConnection
        return PostgresConnection(db_config, ssh_config)
    raise ValueError(f"Unsupported database type: {db_config.db_type}")
