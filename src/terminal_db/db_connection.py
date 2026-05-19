import logging
from typing import Optional, Any
import oracledb
from terminal_db.config import DbConfig, SshConfig
from terminal_db.ssh_tunnel import SshTunnel

logger = logging.getLogger(__name__)

MODE_MAP = {
    "NORMAL": oracledb.AUTH_MODE_DEFAULT,
    "SYSDBA": oracledb.AUTH_MODE_SYSDBA,
    "SYSOPER": oracledb.AUTH_MODE_SYSOPER,
}


class DatabaseConnection:
    def __init__(self, db_config: DbConfig, ssh_config: Optional[SshConfig] = None):
        self.db_config = db_config
        self.ssh_config = ssh_config
        self._ssh_tunnel: Optional[SshTunnel] = None
        self._connection: Optional[oracledb.Connection] = None
        self._connected = False

    def connect(self) -> None:
        host = self.db_config.host
        port = self.db_config.port

        if self.ssh_config and self.ssh_config.enabled:
            self._ssh_tunnel = SshTunnel(
                config=self.ssh_config,
                remote_host=host,
                remote_port=port,
            )
            local_port = self._ssh_tunnel.start()
            host = "127.0.0.1"
            port = local_port

        dsn = self._build_dsn(host, port)
        mode = MODE_MAP.get(self.db_config.mode, oracledb.AUTH_MODE_DEFAULT)

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
        else:
            return f"{host}:{port}"

    @property
    def connection(self) -> oracledb.Connection:
        if self._connection is None:
            raise RuntimeError("Not connected to database")
        return self._connection

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

    def get_server_version(self) -> str:
        if self._connection is None:
            return "Not connected"
        try:
            return self._connection.version
        except Exception:
            return "Unknown"
