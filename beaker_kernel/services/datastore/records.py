from collections.abc import MutableMapping
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    from jupyter_client.multikernelmanager import MultiKernelManager
    from . import DatastoreTable, Column, ColumnType

_table_cache = ContextVar("_table_cache", default=None)

def table_cache(table):
    cache = _table_cache.get()
    if cache is None:
        cache = {}
        _table_cache.set(cache)
    return cache.setdefault(table, {})

class TableDict(MutableMapping):
    parent: "MultiKernelManager"
    table: "DatastoreTable"
    pk_cols: "list[Column]"
    pk: "tuple[Column] | Column"
    _cache: ContextVar

    @property
    def cache(self):
        return table_cache(self.table.name)

    def __init__(self, table: "DatastoreTable", parent: "MultiKernelManager" = None, **kwargs):
        super().__init__(**kwargs)
        self.table = table
        self.parent = parent
        self.pk_cols = tuple(col for col in self.table.columns if col.primary_key)
        match len(self.pk_cols):
            case 0:
                raise ValueError("The TableDict class requires at least one primary key set on the table")
            case 1:
                self.pk = self.pk_cols[0]
            case _:
                self.pk = self.pk_cols

    def get(self, key, default=None):
        try:
            return self[key]
        except (IndexError, KeyError) as err:
            return default

    def _condition(self, key):
        match key:
            case dict() if set(key.keys()) == set(col.name for col in self.pk_cols):
                query = key
            case tuple() if len(key) == len(self.pk_cols):
                query = dict(zip(col.name for col in self.pk_cols), key)
            case _ if len(self.pk_cols) == 1:
                query = {self.pk.name: key}
            case _:
                raise ValueError(f"Key {repr(key)} is not a suitable key for this table lookup.")
        return query

    def __getitem__(self, key):
        if key in self.cache:
            return self.cache[key]
        query = self._condition(key)
        item = self.table.get(**query)
        if item is None:
            lookup_str = ", ".join(f"{key}={value}" for key, value in query.items())
            raise KeyError(f"Item with {lookup_str} does not exist in table {self.table.name}")
        if isinstance(item, dict):
            item = self.table.deserialize(item, parent=self.parent)
        self.cache[key] = item
        return item

    def __setitem__(self, key, record):
        conditions = self._condition(key)
        if key in self:
            self.table.update(conditions=conditions, record=record)
        else:
            self.table.add(record)
        if isinstance(record, self.table.resource):
            self.cache[key] = record

    def __contains__(self, key):
        if key in self.cache:
            return True
        try:
            if self[key]:
                return True
        except KeyError:
            return False
        return False

    def __iter__(self):
        for item in self.table.all():
            value = tuple(item[col.name] for col in self.pk_cols)
            if len(self.pk_cols) == 1:
                value = value[0]
            yield value

    def __delitem__(self, key):
        query = self._condition(key)
        self.table.remove(**query)
        del self.cache[key]

    def __len__(self):
        return self.table.count()

    def clear(self):
        # Log warning
        return None

class TableDictRecord(dict):
    table: TableDict

    def __init__(self, table: TableDict, **kwargs):
        self.table = table
        super().__init__(**kwargs)

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        self.callback(f"Set item: {key} = {value}")

    def __delitem__(self, key):
        value = self[key]
        super().__delitem__(key)
        self.callback(f"Deleted item: {key} (was {value})")

    def clear(self):
        super().clear()
        self.callback("Dictionary cleared")

    def pop(self, key, *args):
        result = super().pop(key, *args)
        self.callback(f"Popped item: {key}")
        return result

    def popitem(self):
        result = super().popitem()
        self.callback(f"Popped item pair: {result}")
        return result

    def update(self, *args, **kwargs):
        super().update(*args, **kwargs)
        self.callback("Dictionary updated via update() method")

    def __del__(self):
        # Ensure updated before deletion
        super().__del__()
