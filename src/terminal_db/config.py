from pydantic import BaseModel, Field
from typing import Optional


class SshConfig(BaseModel):
    enabled: bool = False
    host: str = ""
    port: int = 22
    username: str = ""
    key_path: Optional[str] = None
    password: Optional[str] = None


class DbConfig(BaseModel):
    db_type: str = "oracle"
    host: str = ""
    port: int = 1521
    service_name: str = ""
    sid: Optional[str] = None
    username: str = ""
    password: str = ""
    mode: str = "NORMAL"  # NORMAL, SYSDBA, SYSOPER


class ConnectionProfile(BaseModel):
    name: str = ""
    db: DbConfig
    ssh: SshConfig = Field(default_factory=SshConfig)
