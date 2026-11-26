"""Initial schema for a fresh Compose volume, plus additive upgrades in place."""

from sqlalchemy import inspect, text

from src.models.account import Account
from src.models.audit import Event
from src.models.dataset import Dataset
from src.models.dispatch import Dispatch, DispatchList
from src.models.night import Night
from src.models.review import Review
from src.models.run import Run

SCHEMA = (Account, Dataset, Run, Review, Event, Night, DispatchList, Dispatch)

# Columns added after the first release; create_all never alters an existing table.
ADDED_COLUMNS = {
    "runs": (("night_id", "VARCHAR(36) REFERENCES nights(id)"),),
}


def migrate(engine):
    tables = [model.__table__ for model in SCHEMA]
    Account.metadata.create_all(engine, tables=tables)
    existing = inspect(engine)
    with engine.begin() as connection:
        for table, columns in ADDED_COLUMNS.items():
            if not existing.has_table(table):
                continue
            present = {column["name"] for column in existing.get_columns(table)}
            for name, definition in columns:
                if name not in present:
                    connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {definition}"))
