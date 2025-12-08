# Beaker Datastore

A lightweight, pluggable datastore abstraction layer for Beaker that provides a unified interface for multiple database backends.

## Overview

The Beaker datastore system provides a consistent API for storing and retrieving data across different database backends:

- **SQLite** - Lightweight, file-based SQL database (default)
- **PostgreSQL** - Production-grade SQL database
- **DynamoDB** - AWS NoSQL database service

All backends share a common session-based interface, making it easy to switch between databases without changing your application code.

## Architecture

```
BeakerDatastore (Abstract Base)
├── SQLAlchemyDatastore (SQLite + Postgres)
│   └── SQLAlchemySession (dict-based CRUD)
│       └── Uses SQLAlchemy Core (not ORM)
└── DynamoDBDatastore (AWS NoSQL)
    └── DynamoDBSession (boto3 wrapper)

Common Session Protocol:
- add(item: dict)           # Stage item for insertion
- commit()                  # Commit transaction
- rollback()                # Rollback transaction
- close()                   # Close session
- get(pk)                   # Get by primary key
- query(**filters)          # Query with filters
- scan()                    # Scan all items
- update_item(pk, updates)  # Update item
- delete_item(pk)           # Delete item
```

## Design Principles

1. **Dictionary-based operations** - All data is handled as Python dictionaries, not ORM models
2. **Lightweight** - Uses SQLAlchemy Core (SQL expression language) instead of full ORM
3. **No foreign keys** - Each table is independent and self-contained
4. **Simple datatypes** - Only basic types: String, Integer, DateTime, Text, Boolean, JSON
5. **Unified interface** - Same API works across SQL and NoSQL backends
6. **Transaction support** - Context managers for automatic commit/rollback

## Quick Start

### Default SQLite Setup

By default, Beaker uses SQLite with automatic table creation:

```python
# No configuration needed - automatically uses ~/.beaker/beaker.db

# In your code
datastore = app.datastore

# Create data
with datastore.get_session('beaker_sessions') as session:
    session.add({
        'session_id': 'sess-123',
        'kernel_id': 'kern-456',
        'user_id': 'user-789',
        'status': 'active'
    })

# Query data
with datastore.get_session('beaker_sessions') as session:
    session_data = session.get('sess-123')
    active_sessions = session.query(status='active')
```

## Configuration

### SQLite (Default)

```python
# beaker_config.py
c.BaseBeakerApp.datastore_class = "beaker_kernel.services.datastore.sqlite.Sqlite3Datastore"
c.Sqlite3Datastore.database_path = "~/.beaker/beaker.db"
```

### PostgreSQL

```python
# beaker_config.py
c.BaseBeakerApp.datastore_class = "beaker_kernel.services.datastore.sqlalchemy.SQLAlchemyDatastore"
c.SQLAlchemyDatastore.database_url = "postgresql://user:password@localhost:5432/beaker"
```

### DynamoDB

```python
# beaker_config.py
c.BaseBeakerApp.datastore_class = "beaker_kernel.services.datastore.dynamodb.DynamoDBDatastore"
c.DynamoDBDatastore.table_name = "beaker-sessions"
c.DynamoDBDatastore.region_name = "us-east-1"

# For local DynamoDB
c.DynamoDBDatastore.use_local = True  # Uses http://localhost:8000
```

## Usage Examples

### Basic CRUD Operations

```python
# Create
with datastore.get_session('beaker_sessions') as session:
    session.add({
        'session_id': 'sess-abc123',
        'kernel_id': 'kern-xyz789',
        'user_id': 'user-001',
        'notebook_path': '/notebooks/analysis.ipynb',
        'status': 'active',
        'metadata': {'project': 'data-analysis'}
    })
    # Automatically commits on context exit

# Read - Get by primary key
with datastore.get_session('beaker_sessions') as session:
    session_data = session.get('sess-abc123')
    print(session_data)
    # {'session_id': 'sess-abc123', 'kernel_id': 'kern-xyz789', ...}

# Read - Query with filters
with datastore.get_session('beaker_sessions') as session:
    active_sessions = session.query(status='active', user_id='user-001')
    for sess in active_sessions:
        print(f"Session {sess['session_id']}: {sess['status']}")

# Update
with datastore.get_session('beaker_sessions') as session:
    session.update_item('sess-abc123', {
        'status': 'closed',
        'last_activity': datetime.utcnow()
    })

# Delete
with datastore.get_session('beaker_sessions') as session:
    session.delete_item('sess-abc123')
```

### Error Handling

```python
try:
    with datastore.get_session('beaker_sessions') as session:
        session.add({'session_id': 'sess-123', 'status': 'active'})
        # If an exception occurs, transaction is automatically rolled back
        raise ValueError("Something went wrong")
except ValueError:
    print("Transaction was rolled back automatically")
```

### Manual Transaction Control

```python
session = datastore.get_session('beaker_sessions')
try:
    session.add({'session_id': 'sess-123', 'status': 'active'})
    session.add({'session_id': 'sess-456', 'status': 'active'})
    session.commit()
except Exception:
    session.rollback()
    raise
finally:
    session.close()
```

## Included Tables

The datastore comes with one core table pre-configured:

### beaker_sessions
Track active kernel sessions.

| Column | Type | Description |
|--------|------|-------------|
| session_id | String(255) | Primary key - unique session identifier |
| kernel_id | String(255) | Associated kernel ID |
| user_id | String(255) | User who owns this session |
| notebook_path | String(512) | Path to notebook file (nullable) |
| started_at | DateTime | Session start time |
| last_activity | DateTime | Last activity timestamp |
| status | String(50) | Session status (active, closed, etc.) |
| metadata | JSON | Additional metadata (nullable) |

## Defining Custom Tables

You can easily define your own tables using SQLAlchemy Core's `Table` construct:

```python
from datetime import datetime
from sqlalchemy import MetaData, Table, Column, String, Integer, DateTime, Boolean, JSON

# Create metadata instance
metadata = MetaData()

# Define your table
my_custom_table = Table(
    'my_custom_table',
    metadata,
    Column('id', String(255), primary_key=True),
    Column('name', String(255), nullable=False),
    Column('value', Integer, default=0),
    Column('enabled', Boolean, default=True),
    Column('data', JSON, nullable=True),
    Column('created_at', DateTime, default=datetime.utcnow),
)

# Register the table with the datastore
datastore.register_table(my_custom_table)

# Create the table in the database
datastore.create_tables([my_custom_table])

# Use it
with datastore.get_session('my_custom_table') as session:
    session.add({
        'id': 'item-001',
        'name': 'Example Item',
        'value': 42,
        'enabled': True,
        'data': {'key': 'value'}
    })
```

### Guidelines for Custom Tables

1. **Use simple datatypes only**: String, Integer, DateTime, Text, Boolean, JSON
2. **Single primary key**: Always use a single-column primary key (no composite keys)
3. **No foreign keys**: Keep tables independent
4. **Provide defaults**: Use `default=` for timestamp columns
5. **Document columns**: Use the `doc=` parameter to describe each column

## API Reference

### BeakerDatastore

Base class for all datastore implementations.

#### Methods

- **`get_session(table_name: Optional[str]) -> DatastoreSession`**
  - Get a new session for performing operations
  - For SQL datastores, `table_name` is required
  - Returns a session implementing the DatastoreSession protocol

- **`register_table(table: Table) -> None`**
  - Register a table definition with the datastore
  - For SQLAlchemy datastores only

- **`create_tables(tables: Optional[list[Table]]) -> None`**
  - Create tables in the database
  - If `tables` is None, creates all registered tables
  - For SQLAlchemy datastores only

- **`list_tables() -> list[str]`**
  - List all tables in the database

- **`drop_table(table_name: str) -> None`**
  - Drop a table from the database

### DatastoreSession

Protocol defining the session interface.

#### Methods

- **`add(item: dict) -> None`**
  - Stage an item for insertion
  - Does not commit until `commit()` is called

- **`commit() -> None`**
  - Commit all staged changes

- **`rollback() -> None`**
  - Rollback staged changes

- **`close() -> None`**
  - Close the session and clean up resources

- **`get(primary_key: Any) -> Optional[dict]`**
  - Get a single item by primary key
  - Returns None if not found

- **`query(**filters) -> list[dict]`**
  - Query items with filters
  - Filters are column=value pairs
  - Returns list of matching items

- **`scan(**filters) -> list[dict]`**
  - Scan all items, optionally with filters
  - For SQL databases, same as `query()`

- **`update_item(primary_key: Any, updates: dict) -> None`**
  - Update an item by primary key

- **`delete_item(primary_key: Any) -> None`**
  - Delete an item by primary key

## Backend-Specific Features

### SQLite / PostgreSQL (SQLAlchemy)

**Advantages:**
- ACID transactions
- Rich query capabilities
- Standard SQL features
- Easy local development

**Connection Pooling:**
```python
# SQLAlchemy automatically manages connection pooling
c.SQLAlchemyDatastore.echo = True  # Enable SQL query logging for debugging
```

**Database URL Format:**
```python
# SQLite
"sqlite:///path/to/database.db"
"sqlite:////absolute/path/to/database.db"

# PostgreSQL
"postgresql://username:password@host:port/database"
"postgresql+psycopg2://user:pass@localhost/beaker"
```

### DynamoDB

**Advantages:**
- Fully managed (no server maintenance)
- Automatic scaling
- Pay-per-use pricing
- Multi-region replication

**Table Creation:**
```python
datastore.create_table(
    table_name='my_table',
    key_schema=[
        {'AttributeName': 'id', 'KeyType': 'HASH'}
    ],
    attribute_definitions=[
        {'AttributeName': 'id', 'AttributeType': 'S'}
    ],
    BillingMode='PAY_PER_REQUEST'
)
```

**Query with DynamoDB:**
```python
from boto3.dynamodb.conditions import Key

with datastore.get_session() as session:
    response = session.query(
        KeyConditionExpression=Key('user_id').eq('user-123')
    )
    items = response['Items']
```

## Troubleshooting

### SQLite: Database is locked

```python
# Increase timeout for busy database
c.SQLAlchemyDatastore.database_url = "sqlite:///beaker.db?timeout=20"
```

### PostgreSQL: Connection refused

```python
# Check connection parameters
c.SQLAlchemyDatastore.database_url = "postgresql://user:pass@localhost:5432/beaker"
c.SQLAlchemyDatastore.echo = True  # Enable logging to see connection attempts
```

### DynamoDB: ResourceNotFoundException

```python
# Create the table first
datastore.create_table(
    table_name='beaker-sessions',
    key_schema=[{'AttributeName': 'session_id', 'KeyType': 'HASH'}],
    attribute_definitions=[{'AttributeName': 'session_id', 'AttributeType': 'S'}],
    BillingMode='PAY_PER_REQUEST'
)
```

### Table doesn't exist

```python
# Check registered tables
tables = datastore.list_tables()
print(f"Available tables: {tables}")

# Create missing tables
datastore.create_tables()
```

## Performance Tips

1. **Use context managers** - Ensures proper connection cleanup
2. **Batch operations** - Add multiple items in one session
3. **Close sessions** - Always close sessions when done
4. **Index frequently queried columns** - For SQL databases (requires manual schema modification)
5. **Use connection pooling** - SQLAlchemy handles this automatically

## Migration from Old API

If you're migrating from an older Beaker datastore API:

**Old:**
```python
datastore.query("SELECT * FROM sessions WHERE status = ?", {"status": "active"})
```

**New:**
```python
with datastore.get_session('beaker_sessions') as session:
    sessions = session.query(status='active')
```

## Testing

### Using SQLite for Tests

```python
# test_config.py
c.SQLAlchemyDatastore.database_url = "sqlite:///:memory:"  # In-memory database
```

### Mocking the Datastore

```python
from unittest.mock import MagicMock

# Mock the datastore
mock_datastore = MagicMock()
app.datastore = mock_datastore

# Mock a session
mock_session = MagicMock()
mock_datastore.get_session.return_value.__enter__.return_value = mock_session
```

## Contributing

When adding new tables:

1. Define the table in `tables.py` using SQLAlchemy Core `Table` construct
2. Add the table to the `ALL_TABLES` list
3. Document the table structure in this README
4. Write tests for the new table

When adding new backends:

1. Implement the `BeakerDatastore` interface
2. Implement a session class following the `DatastoreSession` protocol
3. Add configuration documentation
4. Add usage examples

## Further Reading

- [SQLAlchemy Core Documentation](https://docs.sqlalchemy.org/en/20/core/)
- [Boto3 DynamoDB Documentation](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/dynamodb.html)
- [Beaker Kernel Documentation](../../README.md)
