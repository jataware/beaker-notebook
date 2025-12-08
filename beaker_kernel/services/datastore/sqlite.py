from pathlib import Path
from typing import Any, ClassVar, TypeVar, Generic

from traitlets import Unicode, default, validate, observe

from . import BeakerDatastore, DatastoreTable, ColumnType

try:
    import sqlite3
except ImportError:
    # fallback on pysqlite2 if Python was build without sqlite
    from pysqlite2 import dbapi2 as sqlite3  # type:ignore[no-redef]

class Sqlite3Table(DatastoreTable):
    type_map = {
        ColumnType.BOOL: "BOOLEAN",
        ColumnType.TEXT: "TEXT",
        ColumnType.BLOB: "BLOB",
        ColumnType.JSON: "TEXT",
        ColumnType.INT: "INTEGER",
        ColumnType.FLOAT: "REAL",
        ColumnType.DATETIME: "DATETIME",
    }

    @property
    def cursor(self) -> sqlite3.Cursor:
        return self.datastore.cursor

    def parse_conditions(self, conditions: dict) -> tuple[str, list]:
        query_str = ""
        params = []
        if conditions:
            condition_cols, condition_values = zip(*conditions.items())
            cond_def = " AND ".join([f"{col}=?" for col in condition_cols])
            query_str = f"WHERE {cond_def}"
            params.extend(condition_values)
        return query_str, params

    def create(self):
        """Create the table in the SQLite database."""
        col_lines = []
        for col in self.columns:
            line_parts = [col.name]
            if col.column_type:
                line_parts.append(self.type_map.get(col.column_type, col.column_type))
            if col.primary_key:
                line_parts.append("PRIMARY KEY")
            if col.unique:
                line_parts.append("UNIQUE")
            if not col.allow_null:
                line_parts.append("NOT NULL")
            if col.default_value is not None:
                line_parts.append(f"DEFAULT {col.default_value}")
            col_lines.append(" ".join(line_parts))
        col_def = ',\n   '.join(col_lines)
        query = f"""\
CREATE TABLE IF NOT EXISTS {self.name}
(
    {col_def}
);"""
        self.cursor.execute(query)

    def exists(self):
        """Check if the table exists in the SQLite database."""
        query = f"SELECT name FROM sqlite_master WHERE type='table' AND name=?"
        result = self.cursor.execute(query, (self.name,))
        return bool(result.fetchall())

    def add(self, record_values: dict):
        """Add a new record to the table."""
        columns = list(record_values.keys())
        col_def = ", ".join(columns)
        placeholders = ", ".join(["?" for _ in columns])
        query = f"""INSERT INTO {self.name} ({col_def}) VALUES ({placeholders})"""
        values = [record_values[col] for col in columns]
        self.cursor.execute(query, values)

    def get(self, **conditions: Any):
        """Get a single record matching the conditions."""
        cond_str, cond_params = self.parse_conditions(conditions)
        col_def = ", ".join([col.name for col in self.columns])
        query = f"""SELECT {col_def} FROM {self.name} {cond_str}"""
        self.cursor.execute(query, cond_params)
        result = self.cursor.fetchone()
        return result  # type: ignore[return-value]

    def remove(self, **conditions: Any):
        """Remove records matching the conditions."""
        if not conditions:
            raise ValueError("Removing records require at least one condition")
        cond_str, cond_params = self.parse_conditions(conditions)
        query = f"""DELETE FROM {self.name} {cond_str}"""
        self.cursor.execute(query, cond_params)

    def all(self):
        """Retrieve all records from the table."""
        col_def = ", ".join([col.name for col in self.columns])
        query = f"""SELECT {col_def} FROM {self.name};"""
        self.cursor.execute(query)
        result = self.cursor.fetchall()
        return result  # type: ignore[return-value]

    def filter(self, **conditions: Any):
        """Filter records matching the conditions."""
        col_def = ", ".join([col.name for col in self.columns])
        query = f"""SELECT {col_def} FROM {self.name}"""
        cond_str, params = self.parse_conditions(conditions)
        if cond_str:
            query = f"{query} {cond_str}"
        self.cursor.execute(query, params)
        result = self.cursor.fetchall()
        return result  # type: ignore[return-value]

    def update(self, conditions: dict, values: dict):
        """Update records matching conditions with new values."""
        if not conditions:
            raise ValueError("Updating records require at least one condition")
        cond_str, cond_params = self.parse_conditions(conditions)
        set_clause = ", ".join([f"{col}=?" for col in values.keys()])
        query = f"""UPDATE {self.name} SET {set_clause} {cond_str}"""
        params = list(values.values()) + cond_params
        self.cursor.execute(query, params)



class Sqlite3Datastore(BeakerDatastore):
    """
    SQLite-specific datastore implementation.
    """
    _cursor = None
    _connection = None
    table_class: ClassVar[type] = Sqlite3Table

    database_path = Unicode(
        default_value=":memory:",
        allow_none=True,
        help="Path to SQLite database file (will be converted to database_url)"
    ).tag(config=True)

    @staticmethod
    def dict_factory(cursor, row):
        fields = [column[0] for column in cursor.description]
        return {key: value for key, value in zip(fields, row)}

    @validate("database_path")
    def _validate_database_path(self, proposal):
        if isinstance(proposal.value, str) and not proposal.value.startswith(":"):
            db_path = Path(proposal.value).expanduser().resolve()
            db_path.parent.mkdir(parents=True, exist_ok=True)
            return str(db_path)
        else:
            return proposal

    @property
    def connection(self) -> sqlite3.Connection:
        """Start a database connection"""
        if self._connection is None:
            # Set isolation level to None to autocommit all changes to the database.
            self._connection = sqlite3.connect(self.database_path, isolation_level=None)
            self._connection.row_factory = self.dict_factory
        return self._connection

    @property
    def cursor(self) -> sqlite3.Cursor:
        """Start a cursor and create a database called 'session'"""
        if self._cursor is None:
            self._cursor = self.connection.cursor()
        return self._cursor
