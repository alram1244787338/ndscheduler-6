"""Custom exceptions for the corescheduler package.

Provides clear, actionable error messages for configuration and
datastore problems so failures don't have to be diagnosed by reading
raw tracebacks.
"""


class SchedulerConfigError(ValueError):
    """Raised when the scheduler is given invalid configuration.

    Covers bad SchedulerManager arguments, missing settings keys, or
    internally inconsistent options.
    """


class DatastoreConfigError(ValueError):
    """Raised when a datastore provider receives invalid or incomplete
    connection configuration.

    The message should describe which key(s) are missing or invalid and
    which provider raised the error.
    """


class DatastoreInitError(RuntimeError):
    """Raised when a datastore cannot be instantiated even though the
    configuration looked valid — e.g. the provider class path cannot be
    imported or the singleton is in a broken state.
    """
