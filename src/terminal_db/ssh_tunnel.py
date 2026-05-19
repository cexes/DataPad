import socket
import select
import threading
import logging
from typing import Optional
import paramiko
from terminal_db.config import SshConfig

logger = logging.getLogger(__name__)


class SshTunnel:
    def __init__(self, config: SshConfig, remote_host: str, remote_port: int, local_port: int = 0):
        self.config = config
        self.remote_host = remote_host
        self.remote_port = remote_port
        self.local_port = local_port
        self._server: Optional[socket.socket] = None
        self._client: Optional[paramiko.SSHClient] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._bound_port = 0

    def start(self) -> int:
        self._client = paramiko.SSHClient()
        self._client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        connect_kwargs = {
            "hostname": self.config.host,
            "port": self.config.port,
            "username": self.config.username,
            "timeout": 30,
        }

        if self.config.key_path:
            connect_kwargs["key_filename"] = self.config.key_path
        elif self.config.password:
            connect_kwargs["password"] = self.config.password

        logger.info(f"Connecting to SSH server {self.config.host}:{self.config.port}")
        self._client.connect(**connect_kwargs)

        self._server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server.bind(("127.0.0.1", self.local_port))
        self._server.listen(5)
        self._bound_port = self._server.getsockname()[1]

        self._running = True
        self._thread = threading.Thread(target=self._forward, daemon=True)
        self._thread.start()

        logger.info(f"SSH tunnel started on local port {self._bound_port}")
        return self._bound_port

    def _forward(self):
        while self._running:
            try:
                readable, _, _ = select.select([self._server], [], [], 1.0)
                if not readable:
                    continue

                client_sock, _ = self._server.accept()
                client_sock.settimeout(5.0)

                transport = self._client.get_transport()
                if transport is None:
                    client_sock.close()
                    continue

                channel = transport.open_channel(
                    "direct-tcpip",
                    (self.remote_host, self.remote_port),
                    client_sock.getpeername(),
                )

                threading.Thread(
                    target=self._relay,
                    args=(client_sock, channel),
                    daemon=True,
                ).start()

            except Exception as e:
                logger.error(f"SSH tunnel error: {e}")
                if not self._running:
                    break

    @staticmethod
    def _relay(sock1, chan1):
        try:
            while True:
                r, _, _ = select.select([sock1, chan1], [], [], 5.0)
                if not r:
                    continue
                if sock1 in r:
                    data = sock1.recv(8192)
                    if not data:
                        return
                    chan1.send(data)
                if chan1 in r:
                    data = chan1.recv(8192)
                    if not data:
                        return
                    sock1.send(data)
        except Exception:
            pass
        finally:
            sock1.close()
            chan1.close()

    def stop(self):
        self._running = False
        if self._server:
            try:
                self._server.close()
            except Exception:
                pass
            self._server = None
        if self._client:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        logger.info("SSH tunnel stopped")

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def bound_port(self) -> int:
        return self._bound_port
