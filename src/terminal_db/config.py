from enum import Enum
from pydantic import BaseModel, Field
from typing import Optional


class DbType(str, Enum):
    ORACLE = "oracle"
    POSTGRES = "postgres"


DB_DEFAULT_PORTS = {
    DbType.ORACLE: 1521,
    DbType.POSTGRES: 5432,
}


class SshConfig(BaseModel):
    enabled: bool = False
    host: str = ""
    port: int = 22
    username: str = ""
    key_path: Optional[str] = None
    password: Optional[str] = None


class DbConfig(BaseModel):
    db_type: DbType = DbType.ORACLE
    host: str = ""
    port: int = 1521
    service_name: str = ""
    sid: Optional[str] = None
    username: str = ""
    password: str = ""
    mode: str = "NORMAL"  # NORMAL, SYSDBA, SYSOPER (Oracle only)


class ConnectionProfile(BaseModel):
    name: str = ""
    db: DbConfig
    ssh: SshConfig = Field(default_factory=SshConfig)
