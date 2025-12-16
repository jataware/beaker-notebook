import datetime
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Optional, Generic, TypeAlias, TypeVar, ClassVar, Union, TypedDict, TYPE_CHECKING, _TypedDict
from collections.abc import Callable
from types import GenericAlias, get_original_bases, resolve_bases

from traitlets import Instance, TraitError, Unicode, validate, MetaHasTraits
from traitlets.config.configurable import LoggingConfigurable

if TYPE_CHECKING:
    from beaker_kernel.app.base import BaseBeakerApp

# RecordType = TypeVar("RecordType", bound="DatastoreRecord", covariant=True)
TableRef = TypeVar("TableRef", bound="DatastoreTable", covariant=True)
# RecordRef = TypeVar("RecordRef", bound="DatastoreTable", covariant=True)

class TableRecord(Generic[TableRef]):
    def __class_getitem__(cls, value: "type[DatastoreTable]"):
        cls_name = f"{value.__name__}Record"
        keydef: dict[str, type] = {
            col.name: ColumnType.to_pytype(col.column_type)
            for col in value.columns
        }
        # from typing import Literal
        # lit: TypeAlias = Literal[*keydef.keys()]
        return TypedDict(cls_name, keydef)
# class TableRecord(type):
#     def __new__(mcls, cls):
#         print(mcls, cls)
#         cls_name = f"{cls.__name__}Record"
#         keydef: dict[str, type] = {
#             col.name: ColumnType.to_pytype(col.column_type)
#             for col in cls.columns
#         }
#         result_class = type(cls_name, (object,), {
#             "__annotations__": keydef,
#             "__orig_bases__": (object,),
#             "__dict__": {key: None for key in keydef},
#             "__getitem__": lambda self, a: f"{self}.{a}",
#             "__setitem__": lambda self, a, b: f"{self}.{a} = {b}",
#         })
#         return result_class
    # def __class_getitem__(cls, value: "DatastoreTable"):
    #     cls_name = f"{value.__name__}Record"
    #     keydef: dict[str, type] = {
    #         col.name: ColumnType.to_pytype(col.column_type)
    #         for col in value.columns
    #     }
    #     return TypedDict(cls_name, keydef)


# Export for convenience
__all__ = [
    'BeakerDatastore',
    'Column',
    'ColumnType',
    # 'DatastoreRecordMeta',
    'DatastoreTable',
    # 'RecordType',
]


class Now():
    """Simple class to indicate default 'now' timestamp in the UTC timezone."""
    def __call__(self):
        return datetime.datetime.now(tz=datetime.timezone.utc)


class ColumnType(StrEnum):
    BOOL     = "boolean"
    BOOLEAN  = "boolean"
    TEXT     = "string"
    BLOB     = "blob"
    JSON     = "json"
    INT      = "integer"
    INTEGER  = "integer"
    FLOAT    = "float"
    DATETIME = "datetime"

    @classmethod
    def to_pytype(cls, value) -> type|None:
        match value:
            case cls.BOOL:
                return bool
            case cls.TEXT:
                return str
            case cls.BLOB:
                return str
            case cls.JSON:
                return str|list|dict
            case cls.INT:
                return int
            case cls.FLOAT:
                return float
            case cls.DATETIME:
                return datetime.datetime|datetime.date
            case _:
                return None


@dataclass
class Column:
    name: str
    column_type: Optional[ColumnType] = field(default=None)
    primary_key: bool = field(default=False)
    unique: bool = field(default=False)
    allow_null: bool = field(default=True)
    default_value: Any = field(default=None)
    extra: dict = field(default_factory=lambda: {})


# class DatastoreRecord(object):
#     _tables: "ClassVar[dict[str, DatastoreTable]]" = {}

#     def __class_getitem__(cls, table):
#         print(f"checking {cls=} for {table=} ({type(table)=})")
#         if table in cls._tables:
#             print("Found it")
#         if isinstance(table, TypeVar):
#             return GenericAlias(DatastoreRecord, (table,))

#         # TODO rename if works
#         subclass = table
#         cls_name = f"{subclass.__name__}Record"
#         keydef: dict[str, type] = {
#             col.name: ColumnType.to_pytype(col.column_type)
#             for col in subclass.columns
#         }
#         result_class = type(cls_name, (DatastoreRecord,), {
#             "__annotations__": keydef,
#             "__orig_bases__": (DatastoreRecord,),
#             "__dict__": {key: None for key in keydef},
#         })
#         cls._tables[cls_name] = result_class
#         return result_class


class DatastoreTable[RecordType]:
    """
    Class that represents a table in the datastore.

    Type Parameters
    ---------------
    TableRef :
        The type of records stored in this table, typically a TypedDict generated
        from the table's column definitions.
    """
    name: ClassVar[str]
    columns: ClassVar[list[Column]]
    resource: ClassVar[type]

    datastore: "BeakerDatastore"
    metadata: dict[str, Any]

    def __new__(cls, *args, datastore: "BeakerDatastore" = None, **kwargs) -> "DatastoreTable[RecordType]":
        """Create a proper table belonging to the defined datastore."""
        # Check if this is a definition of a table rather than a definition of the metaclass
        if issubclass(cls, DatastoreTable) and cls is not DatastoreTable and datastore:
            # Dynamically rewrite the MRO for the class to insert the datastore table class between the final table class
            # and the DatastoreTable definition
            datastore_subclass: type = datastore.table_class
            namespace = dict(vars(cls))
            namespace["__orig_bases__"] = (datastore_subclass, DatastoreTable)
            cls = type(cls.__name__, (datastore_subclass, DatastoreTable), namespace)
            datastore.tables.append(cls)
        instance = super(DatastoreTable, cls).__new__(cls)
        cls.__init__(instance, *args, datastore=datastore, **kwargs)
        return instance

    def __init__(self, datastore=None, metadata=None):
        self.datastore = datastore
        self.metadata = metadata
        if not self.exists():
            self.create()

    def create(self):
        """Create the table in the datastore."""
        raise NotImplementedError()

    def exists(self) -> bool:
        """Check if the table exists in the datastore."""
        raise NotImplementedError()

    def add(self, record: dict|object):
        """Add a new record to the table."""
        raise NotImplementedError()

    def get(self, **conditions: dict) -> RecordType|None:
        """Get a single record matching the conditions."""
        raise NotImplementedError()

    def remove(self, **conditions: str):
        """Remove records matching the conditions."""
        raise NotImplementedError()

    def all(self) -> list[RecordType]:
        """Retrieve all records from the table."""
        raise NotImplementedError()

    def count(self, **conditions: dict) -> int:
        """Count records matching the conditions."""
        raise NotImplementedError()

    def filter(self, **conditions: dict) -> RecordType:
        """Filter records matching the conditions."""
        raise NotImplementedError()

    def update(self, conditions: dict, record: dict|object):
        """Update records matching conditions with new values."""
        raise NotImplementedError()

    def serialize(self, resource) -> "TableRecord":
        # Warning: Do not modify the passed resource during serialization as resource is a shared reference.
        return {
            getattr(resource, col.name) for col in self.columns if hasattr(resource, col.name)
        }

    def deserialize(self, record: "TableRecord", parent=None):
        if hasattr(self, "resource"):
            return self.resource(**record)
        else:
            return record


class BeakerDatastore(LoggingConfigurable):
    """
    Abstract base class for Beaker datastores.

    This class defines the interface that all datastore implementations
    must follow, providing a unified API for both SQL and NoSQL backends.

    Subclasses should implement:
    - list_tables() -> list[str]
    - drop_table(table_name: str) -> None
    """

    tables: ClassVar[list[type]] = []
    table_class: ClassVar[type]

    parent: "Instance[BaseBeakerApp | None] | BaseBeakerApp"

    def list_tables(self) -> list[str]:
        """
        List all tables in the datastore.

        Returns:
            List of table names
        """
        return [table.name for table in self.tables]

    def drop_table(self, table_name: str) -> None:
        """
        Drop a table from the datastore.

        Args:
            table_name: Name of the table to drop

        Raises:
            NotImplementedError: If not implemented by subclass
        """
        raise NotImplementedError()
