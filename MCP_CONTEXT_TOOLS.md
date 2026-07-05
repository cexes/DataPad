# MCP Context Tools — Implementation Guide

Tools to give the LLM rich schema context, enabling accurate query generation without guessing column names or relationships.

## Pattern

Every new tool touches 3 files in the same way:

```
query_executor.py  → SQL queries (Oracle + Postgres) + method on QueryExecutor
server.py          → @mcp.tool() registration
mcp_config.py      → add name to ALL_TOOLS
```

---

## Tools

### 1. `get_full_schema`

Returns all tables with all their columns and types in a single call.
This is the most important one — unlocks everything else.

**`query_executor.py`**

```python
ORACLE_FULL_SCHEMA_QUERY = """
    SELECT t.table_name, c.column_name, c.data_type, c.nullable, c.data_length
    FROM user_tables t
    JOIN user_tab_columns c ON c.table_name = t.table_name
    ORDER BY t.table_name, c.column_id
"""

POSTGRES_FULL_SCHEMA_QUERY = """
    SELECT t.tablename AS table_name, c.column_name, c.data_type,
           c.is_nullable AS nullable,
           COALESCE(c.character_maximum_length, c.numeric_precision, 0) AS data_length
    FROM pg_catalog.pg_tables t
    JOIN information_schema.columns c ON c.table_name = t.tablename
    WHERE t.schemaname NOT IN ('pg_catalog', 'information_schema')
    ORDER BY t.tablename, c.ordinal_position
"""

# in QueryExecutor class:
def get_full_schema(self) -> QueryResult:
    query = ORACLE_FULL_SCHEMA_QUERY if self._is_oracle() else POSTGRES_FULL_SCHEMA_QUERY
    return self.execute(query)
```

**`server.py`**

```python
if "get_full_schema" in cfg.allowed_tools:
    @mcp.tool()
    def get_full_schema() -> list[dict]:
        """Return full database schema: all tables with columns and data types."""
        error = _ensure_connected()
        if error:
            raise RuntimeError(error)
        result = _executor.get_full_schema()
        if result.error:
            raise RuntimeError(result.error)
        return [dict(zip(result.columns, row)) for row in result.rows]
```

---

### 2. `get_relationships`

Returns foreign key relationships so the LLM understands how to JOIN tables correctly.

**`query_executor.py`**

```python
ORACLE_RELATIONSHIPS_QUERY = """
    SELECT
        uc.table_name AS from_table,
        ucc.column_name AS from_column,
        uc2.table_name AS to_table,
        ucc2.column_name AS to_column
    FROM user_constraints uc
    JOIN user_cons_columns ucc ON ucc.constraint_name = uc.constraint_name
    JOIN user_constraints uc2 ON uc2.constraint_name = uc.r_constraint_name
    JOIN user_cons_columns ucc2 ON ucc2.constraint_name = uc2.constraint_name
    WHERE uc.constraint_type = 'R'
    ORDER BY uc.table_name
"""

POSTGRES_RELATIONSHIPS_QUERY = """
    SELECT
        tc.table_name AS from_table,
        kcu.column_name AS from_column,
        ccu.table_name AS to_table,
        ccu.column_name AS to_column
    FROM information_schema.table_constraints tc
    JOIN information_schema.key_column_usage kcu
        ON kcu.constraint_name = tc.constraint_name
    JOIN information_schema.referential_constraints rc
        ON rc.constraint_name = tc.constraint_name
    JOIN information_schema.constraint_column_usage ccu
        ON ccu.constraint_name = rc.unique_constraint_name
    WHERE tc.constraint_type = 'FOREIGN KEY'
    ORDER BY tc.table_name
"""

# in QueryExecutor class:
def get_relationships(self) -> QueryResult:
    query = ORACLE_RELATIONSHIPS_QUERY if self._is_oracle() else POSTGRES_RELATIONSHIPS_QUERY
    return self.execute(query)
```

**`server.py`**

```python
if "get_relationships" in cfg.allowed_tools:
    @mcp.tool()
    def get_relationships() -> list[dict]:
        """Return all foreign key relationships between tables."""
        error = _ensure_connected()
        if error:
            raise RuntimeError(error)
        result = _executor.get_relationships()
        if result.error:
            raise RuntimeError(result.error)
        return [dict(zip(result.columns, row)) for row in result.rows]
```

---

### 3. `search_schema`

Search tables or columns by name. Useful on large schemas where `get_full_schema` would return too much noise.

**`query_executor.py`**

```python
ORACLE_SEARCH_SCHEMA_QUERY = """
    SELECT 'TABLE' AS kind, table_name AS name, NULL AS table_name
    FROM user_tables WHERE UPPER(table_name) LIKE UPPER(:1)
    UNION ALL
    SELECT 'COLUMN', column_name, table_name
    FROM user_tab_columns WHERE UPPER(column_name) LIKE UPPER(:2)
    ORDER BY kind, name
"""

POSTGRES_SEARCH_SCHEMA_QUERY = """
    SELECT 'TABLE' AS kind, tablename AS name, NULL AS table_name
    FROM pg_catalog.pg_tables
    WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
      AND tablename ILIKE %s
    UNION ALL
    SELECT 'COLUMN', column_name, table_name
    FROM information_schema.columns
    WHERE column_name ILIKE %s
    ORDER BY kind, name
"""

# in QueryExecutor class:
def search_schema(self, term: str) -> QueryResult:
    pattern = f"%{term}%"
    if not self.db.is_connected:
        return QueryResult(error="Not connected to database")
    query = ORACLE_SEARCH_SCHEMA_QUERY if self._is_oracle() else POSTGRES_SEARCH_SCHEMA_QUERY
    cursor = None
    try:
        cursor = self.db.connection.cursor()
        cursor.execute(query, [pattern, pattern])
        columns = [col[0] for col in cursor.description]
        rows = [list(row) for row in cursor.fetchall()]
        return QueryResult(columns=columns, rows=rows, row_count=len(rows), is_select=True)
    except Exception as e:
        return QueryResult(error=str(e))
    finally:
        if cursor:
            try:
                cursor.close()
            except Exception:
                pass
```

**`server.py`**

```python
if "search_schema" in cfg.allowed_tools:
    @mcp.tool()
    def search_schema(term: str) -> list[dict]:
        """Search for tables or columns by name (partial match).

        Args:
            term: Name or partial name to search for
        """
        error = _ensure_connected()
        if error:
            raise RuntimeError(error)
        result = _executor.search_schema(term)
        if result.error:
            raise RuntimeError(result.error)
        return [dict(zip(result.columns, row)) for row in result.rows]
```

---

### 4. `sample_table`

Returns N rows from a table so the LLM understands the actual data format before writing queries.

**`query_executor.py`**

```python
# in QueryExecutor class:
def sample_table(self, table_name: str, limit: int = 5) -> QueryResult:
    if self._is_oracle():
        query = f"SELECT * FROM {table_name} WHERE ROWNUM <= {limit}"
    else:
        query = f"SELECT * FROM {table_name} LIMIT {limit}"
    return self.execute(query)
```

**`server.py`**

```python
if "sample_table" in cfg.allowed_tools:
    @mcp.tool()
    def sample_table(table_name: str, limit: int = 5) -> list[dict]:
        """Return sample rows from a table to understand data shape.

        Args:
            table_name: Table to sample
            limit: Number of rows to return (default 5, max 20)
        """
        error = _ensure_connected()
        if error:
            raise RuntimeError(error)
        limit = min(limit, 20)
        result = _executor.sample_table(table_name, limit)
        if result.error:
            raise RuntimeError(result.error)
        return [dict(zip(result.columns, row)) for row in result.rows]
```

---

### 5. `explain_query`

Returns the execution plan before running. Safety net to catch expensive queries.

**`query_executor.py`**

```python
# in QueryExecutor class:
def explain_query(self, query: str) -> QueryResult:
    query = query.strip().rstrip(";")
    if self._is_oracle():
        explain = f"EXPLAIN PLAN FOR {query}"
        fetch = "SELECT * FROM TABLE(DBMS_XPLAN.DISPLAY)"
        try:
            cursor = self.db.connection.cursor()
            cursor.execute(explain)
            cursor.execute(fetch)
            columns = [col[0] for col in cursor.description]
            rows = [list(row) for row in cursor.fetchall()]
            return QueryResult(columns=columns, rows=rows, row_count=len(rows), is_select=True)
        except Exception as e:
            return QueryResult(error=str(e))
        finally:
            if cursor:
                try:
                    cursor.close()
                except Exception:
                    pass
    else:
        return self.execute(f"EXPLAIN {query}")
```

**`server.py`**

```python
if "explain_query" in cfg.allowed_tools:
    @mcp.tool()
    def explain_query(query: str) -> str:
        """Return the execution plan for a query without running it.

        Args:
            query: SQL query to explain
        """
        error = _ensure_connected()
        if error:
            raise RuntimeError(error)
        result = _executor.explain_query(query)
        if result.error:
            raise RuntimeError(result.error)
        lines = []
        for row in result.rows:
            lines.append(" | ".join(str(v) if v is not None else "" for v in row))
        return "\n".join(lines)
```

---

## `mcp_config.py` — final `ALL_TOOLS`

```python
ALL_TOOLS = [
    "list_connections",
    "connect",
    "list_tables",
    "describe_table",
    "execute_query",
    "get_full_schema",
    "get_relationships",
    "search_schema",
    "sample_table",
    "explain_query",
]
```

---

## Implementation order

1. `get_full_schema` — highest value, implement first
2. `get_relationships` — enables JOIN generation
3. `sample_table` — simple, high impact
4. `search_schema` — useful for large schemas
5. `explain_query` — safety net, implement last
