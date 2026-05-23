import logging
import time
from dataclasses import dataclass, field
from typing import Optional, Any
from terminal_db.config import DbType
from terminal_db.db_connection import DatabaseConnection

logger = logging.getLogger(__name__)


@dataclass
class QueryResult:
    columns: list[str] = field(default_factory=list)
    rows: list[list[Any]] = field(default_factory=list)
    row_count: int = 0
    execution_time: float = 0.0
    error: Optional[str] = None
    is_select: bool = True
    rows_affected: int = 0


ORACLE_TABLES_QUERY = "SELECT table_name FROM user_tables ORDER BY table_name"
POSTGRES_TABLES_QUERY = (
    "SELECT tablename FROM pg_catalog.pg_tables "
    "WHERE schemaname NOT IN ('pg_catalog', 'information_schema') "
    "ORDER BY tablename"
)

ORACLE_COLUMNS_QUERY = (
    "SELECT column_name, data_type, nullable, data_length "
    "FROM user_tab_columns WHERE table_name = :1 "
    "ORDER BY column_id"
)
POSTGRES_COLUMNS_QUERY = (
    "SELECT column_name, data_type, is_nullable, "
    "COALESCE(character_maximum_length, numeric_precision, 0) "
    "FROM information_schema.columns "
    "WHERE table_name = %s "
    "ORDER BY ordinal_position"
)


class QueryExecutor:
    def __init__(self, db_connection: DatabaseConnection, max_rows: int = 1000):
        self.db = db_connection
        self.max_rows = max_rows

    def _is_oracle(self) -> bool:
        return self.db.db_type == DbType.ORACLE

    def execute(self, query: str) -> QueryResult:
        if not self.db.is_connected:
            return QueryResult(error="Not connected to database")

        query = query.strip().rstrip(";")
        if not query:
            return QueryResult(error="Empty query")

        conn = self.db.connection
        cursor = None
        start_time = time.time()

        try:
            cursor = conn.cursor()
            cursor.execute(query)

            if cursor.description:
                columns = [col[0] for col in cursor.description]
                rows = cursor.fetchmany(self.max_rows)
                rows_list = [list(row) for row in rows]
                execution_time = time.time() - start_time

                return QueryResult(
                    columns=columns,
                    rows=rows_list,
                    row_count=len(rows_list),
                    execution_time=execution_time,
                    is_select=True,
                )
            else:
                conn.commit()
                execution_time = time.time() - start_time
                rows_affected = cursor.rowcount

                return QueryResult(
                    execution_time=execution_time,
                    is_select=False,
                    rows_affected=rows_affected,
                )

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Query error: {error_msg}")
            try:
                conn.rollback()
            except Exception:
                pass
            return QueryResult(error=error_msg)

        finally:
            if cursor:
                try:
                    cursor.close()
                except Exception:
                    pass

    def get_tables(self) -> QueryResult:
        query = ORACLE_TABLES_QUERY if self._is_oracle() else POSTGRES_TABLES_QUERY
        return self.execute(query)

    def get_table_columns(self, table_name: str) -> QueryResult:
        if not self.db.is_connected:
            return QueryResult(error="Not connected to database")

        conn = self.db.connection
        cursor = None
        start_time = time.time()

        query = ORACLE_COLUMNS_QUERY if self._is_oracle() else POSTGRES_COLUMNS_QUERY
        params = [table_name]

        try:
            cursor = conn.cursor()
            cursor.execute(query, params)
            columns = [col[0] for col in cursor.description]
            rows = [list(row) for row in cursor.fetchall()]
            return QueryResult(
                columns=columns,
                rows=rows,
                row_count=len(rows),
                execution_time=time.time() - start_time,
                is_select=True,
            )
        except Exception as e:
            return QueryResult(error=str(e))
        finally:
            if cursor:
                try:
                    cursor.close()
                except Exception:
                    pass
