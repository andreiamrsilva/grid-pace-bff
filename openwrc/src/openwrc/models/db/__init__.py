# Import all model modules so their classes register with Base.metadata.
# database.py imports this package, guaranteeing every table is visible
# to create_all regardless of which other modules are in the call chain.
# Add new model modules here when created.
from . import entities, event, itinerary, logs, result  # noqa: F401
