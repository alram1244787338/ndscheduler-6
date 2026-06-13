"""Datastore creation and configuration factory.

Centralises:
- Table-name resolution (defaults merged with user overrides).
- Provider-class loading and instantiation.
- Configuration validation before a connection is attempted.

The previous logic lived partly in ``SchedulerManager.__init__``, partly
in ``DatastoreBase.__init__`` and partly in ``utils.get_datastore_instance``.
This module is now the single place that knows how to wire a datastore
together, so adding a new provider or a new validation rule only touches
this file and the provider itself.
"""

from ndscheduler.corescheduler import constants
from ndscheduler.corescheduler import utils
from ndscheduler.corescheduler.exceptions import (
    DatastoreConfigError,
    DatastoreInitError,
)


# ---------------------------------------------------------------------------
# Table-name resolution
# ---------------------------------------------------------------------------

# Keys the rest of the codebase uses when referring to table names.
_TABLENAME_KEYS = (
    'executions_tablename',
    'jobs_tablename',
    'auditlogs_tablename',
)

_DEFAULT_TABLENAMES = {
    'executions_tablename': constants.DEFAULT_EXECUTIONS_TABLENAME,
    'jobs_tablename': constants.DEFAULT_JOBS_TABLENAME,
    'auditlogs_tablename': constants.DEFAULT_AUDIT_LOGS_TABLENAME,
}


def resolve_table_names(table_names=None):
    """Return a complete table-name dict, filling in defaults for any
    keys the caller did not supply.

    :param table_names: Optional dict with any subset of the recognised
        tablename keys.  ``None`` (or an empty dict) yields all defaults.
    :return: A dict with all three tablename keys populated.
    :rtype: dict
    :raises DatastoreConfigError: If *table_names* contains keys that
        are not recognised — typos are a common source of silent bugs.
    """
    if not table_names:
        return dict(_DEFAULT_TABLENAMES)

    if not isinstance(table_names, dict):
        raise DatastoreConfigError(
            "table_names must be a dict, got %s: %r"
            % (type(table_names).__name__, table_names)
        )

    unknown = set(table_names) - set(_TABLENAME_KEYS)
    if unknown:
        raise DatastoreConfigError(
            "Unknown table-name key(s): %s. Recognised keys are: %s"
            % (sorted(unknown), sorted(_TABLENAME_KEYS))
        )

    resolved = dict(_DEFAULT_TABLENAMES)
    resolved.update(table_names)
    return resolved


# ---------------------------------------------------------------------------
# Provider loading
# ---------------------------------------------------------------------------

def _load_provider_class(datastore_class_path):
    """Import and return the datastore class for the given dotted path.

    :raises DatastoreInitError: if the import fails.
    """
    if not datastore_class_path or not isinstance(datastore_class_path, str):
        raise DatastoreConfigError(
            "datastore_class_path must be a non-empty string, got %r"
            % (datastore_class_path,)
        )
    try:
        return utils.import_from_path(datastore_class_path)
    except (ImportError, AttributeError, IndexError) as exc:
        raise DatastoreInitError(
            "Cannot import datastore class from path %r: %s"
            % (datastore_class_path, exc)
        )


# ---------------------------------------------------------------------------
# Public factory
# ---------------------------------------------------------------------------

def create_datastore(datastore_class_path, db_config=None, table_names=None):
    """Build (or return the cached singleton of) a datastore instance.

    This is the *only* entry point that ``SchedulerManager`` and friends
    should use to obtain a datastore — don't call
    ``DatastoreBase.get_instance`` directly from the scheduler layer.

    :param str datastore_class_path: Dotted import path for the provider
        class, e.g.
        ``'ndscheduler.corescheduler.datastore.providers.sqlite.DatastoreSqlite'``.
    :param dict db_config: Provider-specific connection dict.
    :param dict table_names: Optional table-name overrides; missing keys
        fall back to defaults in ``constants``.
    :return: A ready-to-use ``DatastoreBase`` subclass instance.
    :raises DatastoreConfigError: on invalid arguments.
    :raises DatastoreInitError: if the provider class cannot be loaded.
    """
    provider_cls = _load_provider_class(datastore_class_path)

    resolved_tables = resolve_table_names(table_names)

    # Let the provider validate its own config before we try to connect.
    provider_cls.validate_config(db_config)

    return provider_cls.get_instance(db_config, resolved_tables)
