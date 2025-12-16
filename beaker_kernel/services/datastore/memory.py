import json
import os
import threading
from pathlib import Path
from typing import Any, ClassVar, TypeVar, Generic
from urllib.parse import urlparse, parse_qs, ParseResult, urlunparse

from traitlets import Unicode, default, validate, observe

from . import BeakerDatastore, DatastoreTable, ColumnType, Now

class MemoryTable(DatastoreTable):
    datastore: "MemoryDatastore"
    records: list[dict]
    indexes: dict[str, list]

    def __init__(self, datastore=None, metadata=None):
        self.records = []
        self.indexes = {}
        super().__init__(datastore, metadata)

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
        """No-op as table always exists."""
        pass

    def exists(self):
        """In memory table always exists as part of a table instance."""
        return True

    def add(self, record_values: dict):
        """Add a new record to the table."""
        # TODO: Sanitize record to only what is defined by columns?

        # Fill in any default values that aren't defined in the record
        for col in self.columns:
            if col.default_value and col.name not in record_values:
                if callable(col.default_value):
                    record_values[col.name] = col.default_value()
                else:
                    record_values[col.name] = col.default_value

        self.records.append(record_values)

    def get(self, **conditions: Any):
        """Get a single (first) record matching the conditions."""
        result = []
        for record in self.records:
            for cond_col, cond_val in conditions.items():
                if record.get(cond_col, "_MISSING_") == cond_val:
                    return record
        return None

    def remove(self, **conditions: Any):
        """Remove records matching the conditions."""
        if not conditions:
            raise ValueError("Removing records require at least one condition")
        for idx in range(len(self.records)-1, -1, -1):
            record = self.records[idx]
            for cond_col, cond_val in conditions.items():
                if record.get(cond_col, "_MISSING_") == cond_val:
                    del self.records[idx]

    def all(self):
        """Retrieve all records from the table."""
        return self.records[:]

    def count(self, **conditions: Any):
        return len(self.filter(**conditions))

    def filter(self, **conditions: Any):
        """Filter records matching the conditions."""
        result = []
        for record in self.records:
            for cond_col, cond_val in conditions.items():
                if record.get(cond_col, "_MISSING_") == cond_val:
                    result.append(record)
        return result

    def update(self, conditions: dict, record: dict|object):
        """Update records matching conditions with new values."""
        if not conditions:
            raise ValueError("Updating records require at least one condition")

        col_map = {col.name: col.column_type for col in self.columns}
        if isinstance(record, dict):
            values = {key: value for key, value in record.items() if key in col_map}
        elif isinstance(record, self.resource) and callable(getattr(self, "serialize", None)):
            values = self.serialize(record)
        else:
            values = {col: getattr(record, col) for col in col_map.keys()}

        for cond_record in self.records:
            for cond_col, cond_val in conditions.items():
                if cond_record.get(cond_col, "_MISSING_") == cond_val:
                    cond_record.update(values)


class MemoryDatastore(BeakerDatastore):
    """
    In-memory datastore implementation.
    """
    table_class: ClassVar[type] = MemoryTable

    def drop_table(self, table_name):
        """No-op"""
        pass
