import json
import os
import threading
from pathlib import Path
from typing import Any, ClassVar, TypeVar, Generic
from urllib.parse import urlparse, parse_qs, ParseResult, urlunparse

from traitlets import Unicode, default, validate, observe

from . import BeakerDatastore, DatastoreTable, ColumnType, Now

try:
    import sqlite3
except ImportError:
    # fallback on pysqlite2 if Python was build without sqlite
    from pysqlite2 import dbapi2 as sqlite3  # type:ignore[no-redef]

connection_cache: dict[tuple[int, int], sqlite3.Connection] = {}

class Sqlite3Table(DatastoreTable):
    datastore: "Sqlite3Datastore"
    type_map = {
        ColumnType.BOOL: "BOOLEAN",
        ColumnType.TEXT: "TEXT",
        ColumnType.BLOB: "BLOB",
        ColumnType.JSON: "TEXT",
        ColumnType.INT: "INTEGER",
        ColumnType.FLOAT: "REAL",
        ColumnType.DATETIME: "DATETIME",
    }

    def cursor(self) -> sqlite3.Cursor:
        return self.datastore.cursor()

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
                if isinstance(col.default_value, Now) or col.default_value is Now:
                    # SQLite always stores UTC
                    line_parts.append(f"DEFAULT (DATETIME('now'))")
                else:
                    line_parts.append(f"DEFAULT {repr(col.default_value)}")
            col_lines.append(" ".join(line_parts))
        col_def = ',\n   '.join(col_lines)
        query = f"""\
CREATE TABLE IF NOT EXISTS {self.name}
(
    {col_def}
);"""
        self.cursor().execute(query)

    def exists(self):
        """Check if the table exists in the SQLite database."""
        query = f"SELECT name FROM sqlite_master WHERE type='table' AND name=?"
        cursor = self.cursor()
        cursor.execute(query, (self.name,))
        return bool(cursor.fetchall())

    def sanitize_record(self, column_type: ColumnType, value: Any):
        match column_type:
            case ColumnType.JSON:
                return json.dumps(value)
            case _:
                return value

    def add(self, record: dict|object):
        """Add a new record to the table."""
        col_map = {col.name: col.column_type for col in self.columns}

        if isinstance(record, dict):
            clean_record = {key: value for key, value in record.items() if key in col_map}
        elif isinstance(record, self.resource) and callable(getattr(self, "serialize", None)):
            clean_record = self.serialize(record)
        else:
            clean_record = {col: getattr(record, col) for col in col_map.keys()}

        col_def = ", ".join(clean_record.keys())
        placeholders = ", ".join(["?" for _ in clean_record])
        query = f"""INSERT INTO {self.name} ({col_def}) VALUES ({placeholders})"""
        values = [
            self.sanitize_record(col_map[col_name], value)
            for col_name, value in clean_record.items()
        ]
        try:
            self.cursor().execute(query, values)
        except Exception as err:
            print(err)
            print(query, values)
            raise

    def get(self, **conditions: Any):
        """Get a single record matching the conditions."""
        cond_str, cond_params = self.parse_conditions(conditions)
        col_def = ", ".join([col.name for col in self.columns])
        query = f"""SELECT {col_def} FROM {self.name} {cond_str}"""
        cursor = self.cursor()
        cursor.execute(query, cond_params)
        result = cursor.fetchone()
        if not result:
            result = None
        return result  # type: ignore[return-value]

    def remove(self, **conditions: Any):
        """Remove records matching the conditions."""
        if not conditions:
            raise ValueError("Removing records require at least one condition")
        cond_str, cond_params = self.parse_conditions(conditions)
        query = f"""DELETE FROM {self.name} {cond_str}"""
        self.cursor().execute(query, cond_params)

    def all(self):
        """Retrieve all records from the table."""
        col_def = ", ".join([col.name for col in self.columns])
        query = f"""SELECT {col_def} FROM {self.name};"""
        cursor = self.cursor()
        cursor.execute(query)
        result = cursor.fetchall()
        return result  # type: ignore[return-value]

    def count(self, **conditions: Any):
        query = f"""SELECT COUNT(1) as count FROM {self.name}"""
        cond_str, params = self.parse_conditions(conditions)
        if cond_str:
            query = f"{query} {cond_str}"
        cursor = self.cursor()
        cursor.execute(query, params)
        result = cursor.fetchone()
        return result["count"]

    def filter(self, **conditions: Any):
        """Filter records matching the conditions."""
        col_def = ", ".join([col.name for col in self.columns])
        query = f"""SELECT {col_def} FROM {self.name}"""
        cond_str, params = self.parse_conditions(conditions)
        if cond_str:
            query = f"{query} {cond_str}"
        try:
            cursor = self.cursor()
            cursor.execute(query, params)
            result = cursor.fetchall()
        except Exception as e:
            raise
        return result  # type: ignore[return-value]

    def update(self, conditions: dict, record: dict|object):
        """Update records matching conditions with new values."""
        if not conditions:
            raise ValueError("Updating records require at least one condition")

        col_map = {col.name: col.column_type for col in self.columns}
        if isinstance(record, dict):
            values = {
                key: self.sanitize_record(col_map[key], value)
                for key, value in record.items()
                if key in col_map
            }
        elif isinstance(record, self.resource) and callable(getattr(self, "serialize", None)):
            values = {
                key: self.sanitize_record(col_map[key], value)
                for key, value in self.serialize(record).items()
            }
        else:
            values = {
                col: self.sanitize_record(col, getattr(record, col))
                for col in col_map.keys()
            }

        cond_str, cond_params = self.parse_conditions(conditions)
        set_clause = ", ".join([f"{col}=?" for col in values.keys()])
        query = f"""UPDATE {self.name} SET {set_clause} {cond_str}"""
        params = list(values.values()) + cond_params
        self.cursor().execute(query, params)



class Sqlite3Datastore(BeakerDatastore):
    """
    SQLite-specific datastore implementation.
    """
    _connection = None
    table_class: ClassVar[type] = Sqlite3Table

    database_path = Unicode(
        default_value="file:beaker_datastore?mode=memory&cache=shared",
        allow_none=True,
        help="Path to SQLite database file (will be converted to database_url)"
    ).tag(config=True)

    @staticmethod
    def dict_factory(cursor, row):
        fields = [column[0] for column in cursor.description]
        return {key: value for key, value in zip(fields, row)}

    @validate("database_path")
    def _validate_database_path(self, proposal):
        # Always pass strings starting with ':' unchanged
        if proposal.value.startswith(":"):
            return proposal.value

        parse_result: ParseResult = urlparse(proposal.value)
        query_dict = parse_qs(parse_result.query)
        if query_dict.get("mode", None) == "memory":
            return proposal.value
        else:
            db_path = Path(parse_result.path).expanduser().resolve()
            db_path.parent.mkdir(parents=True, exist_ok=True)
            parse_result = parse_result._replace(scheme="file", path=str(db_path))
            return urlunparse(parse_result)

    @property
    def connection(self) -> sqlite3.Connection:
        """Start a database connection"""
        pid = os.getpid()
        thread_id = threading.get_ident()

        # If the db is in-memory, update path to allow multiple threads/processes to access the same
        # shared in-memory SQLite db
        if self.database_path == ':memory:':
            self.database_path = "file:beaker_datastore?mode=memory&cache=shared"

        if (pid, thread_id) not in connection_cache:
            self.log.debug(f"SQLite3 connection: {pid=}, {thread_id=}, {self.database_path=}, uri={self.database_path.startswith('file:')}")
            connection = sqlite3.connect(
                database=self.database_path,
                isolation_level=None,
                uri=self.database_path.startswith('file:'),
            )
            connection.row_factory = self.dict_factory
            connection_cache[(pid, thread_id)] = connection
        return connection_cache[(pid, thread_id)]

    def cursor(self) -> sqlite3.Cursor:
        """Start a cursor"""
        return self.connection.cursor()

    def list_tables(self):
        """Check if the table exists in the SQLite database."""
        query = f"SELECT name FROM sqlite_master WHERE type='table'"
        cursor = self.cursor()
        cursor.execute(query)
        return [row.name for row in cursor.fetchall()]

    def drop_table(self, table_name):
        query = f"DROP table ?"
        cursor = self.cursor()
        cursor.execute(query, (table_name,))
        return cursor.fetchone()
