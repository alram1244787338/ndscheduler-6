"""Base class to represent datastore.

Responsibilities of this class (and *only* this class at the datastore
layer):

- Own the SQLAlchemy ``MetaData`` / engine / session for the job-store,
  execution and audit-log tables.
- Provide CRUD helpers for executions and audit logs.
- Expose a ``validate_config`` hook that providers override to fail
  early on bad connection dicts.

Table-name resolution and provider loading live in
``ndscheduler.corescheduler.datastore.factory`` — don't duplicate them
here.
"""

import logging

import dateutil.tz
import dateutil.parser
from apscheduler.jobstores import sqlalchemy as sched_sqlalchemy
from sqlalchemy import desc, select, MetaData

from ndscheduler.corescheduler import constants
from ndscheduler.corescheduler import utils
from ndscheduler.corescheduler.datastore import tables
from ndscheduler.corescheduler.exceptions import (
    DatastoreConfigError,
    DatastoreInitError,
)

logger = logging.getLogger(__name__)


def _resolve_table_names(table_names):
    """Fill in defaults for any missing table-name keys.

    Kept local (rather than importing from factory) so that
    ``DatastoreBase`` does not depend on the factory module at import
    time — callers can still construct a datastore directly for tests.
    """
    defaults = {
        'executions_tablename': constants.DEFAULT_EXECUTIONS_TABLENAME,
        'jobs_tablename': constants.DEFAULT_JOBS_TABLENAME,
        'auditlogs_tablename': constants.DEFAULT_AUDIT_LOGS_TABLENAME,
    }
    if not table_names:
        return defaults
    resolved = dict(defaults)
    for key in ('executions_tablename', 'jobs_tablename', 'auditlogs_tablename'):
        if key in table_names:
            resolved[key] = table_names[key]
    return resolved


class DatastoreBase(sched_sqlalchemy.SQLAlchemyJobStore):

    instance = None

    # Connection keys a provider requires in ``db_config``. An empty tuple
    # means "no required keys" (e.g. sqlite). Subclasses override this single
    # tuple instead of re-implementing ``validate_config`` -- so a new key
    # can't be added to one provider and forgotten on the others.
    REQUIRED_CONFIG_KEYS = ()

    @classmethod
    def get_instance(cls, db_config=None, table_names=None):
        """Return the singleton instance for this provider, creating it
        if necessary.

        :param dict db_config: Provider-specific connection dict.
        :param dict table_names: Optional table-name overrides.
        """
        if not cls.instance:
            cls.instance = cls(db_config, table_names)
        return cls.instance

    @classmethod
    def destroy_instance(cls):
        cls.instance = None

    @classmethod
    def validate_config(cls, db_config):
        """Validate *db_config* before a connection is attempted.

        The default implementation is driven by the provider's
        ``REQUIRED_CONFIG_KEYS`` class attribute, so a new provider only has
        to declare that tuple instead of re-implementing the same
        dict / missing-key / port-type checks. This keeps the connection-
        config rules in one place across sqlite / mysql / postgres.

        Providers with extra, provider-specific rules (e.g. sqlite's optional
        ``file_path``) may override this and call ``super().validate_config``
        first.

        :param dict db_config: provider connection settings to validate.
        :raises DatastoreConfigError: with an actionable message naming the
            offending key(s) and provider.
        """
        required = cls.REQUIRED_CONFIG_KEYS
        if not required:
            # Providers such as sqlite need no keys: accept None or a dict.
            if db_config is not None and not isinstance(db_config, dict):
                raise DatastoreConfigError(
                    "%s: db_config must be a dict or None, got %s: %r"
                    % (cls.__name__, type(db_config).__name__, db_config))
            return

        if not isinstance(db_config, dict):
            raise DatastoreConfigError(
                "%s: db_config must be a dict with keys %s, got %r"
                % (cls.__name__, list(required), db_config))

        missing = [key for key in required if key not in db_config]
        if missing:
            raise DatastoreConfigError(
                "%s: db_config is missing required key(s): %s. Expected keys: %s"
                % (cls.__name__, missing, list(required)))

        if 'port' in required and not isinstance(db_config.get('port'), int):
            raise DatastoreConfigError(
                "%s: 'port' must be an int, got %r"
                % (cls.__name__, db_config.get('port')))

    def __init__(self, db_config, table_names):
        """
        :param dict db_config: dictionary containing values for db connection
        :param dict table_names: dictionary containing the names for the jobs,
            executions, or audit logs table, e.g. {
                'executions_tablename': 'scheduler_executions',
                'jobs_tablename': 'scheduler_jobs',
                'auditlogs_tablename': 'scheduler_auditlogs'
            }
            Missing keys are filled with defaults from ``constants``.
        """
        self.metadata = MetaData()
        self.table_names = _resolve_table_names(table_names)
        self.db_config = db_config

        executions_tablename = self.table_names['executions_tablename']
        jobs_tablename = self.table_names['jobs_tablename']
        auditlogs_tablename = self.table_names['auditlogs_tablename']

        self.executions_table = tables.get_execution_table(self.metadata, executions_tablename)
        self.auditlogs_table = tables.get_auditlogs_table(self.metadata, auditlogs_tablename)

        try:
            db_url = self.get_db_url()
        except KeyError as exc:
            raise DatastoreConfigError(
                "%s.get_db_url() is missing a required db_config key: %s. "
                "Check the DATABASE_CONFIG_DICT for this provider."
                % (type(self).__name__, exc)
            )
        except Exception as exc:
            raise DatastoreInitError(
                "%s.get_db_url() failed: %s" % (type(self).__name__, exc)
            )

        try:
            super(DatastoreBase, self).__init__(url=db_url, tablename=jobs_tablename)
            self.metadata.create_all(self.engine)
        except Exception as exc:
            raise DatastoreInitError(
                "Failed to initialise %s with url %r: %s"
                % (type(self).__name__, db_url, exc)
            )

    def get_db_url(self):
        """We can use the dict passed from db_config_dict to construct a db url.
        :return: Database url. See: http://docs.sqlalchemy.org/en/latest/core/engines.html
        :rtype: str
        """
        raise NotImplementedError('Please implement this function.')

    def add_execution(self, execution_id, job_id, state, **kwargs):
        """Insert a record of execution to database.
        :param str execution_id: Execution id.
        :param str job_id: Job id.
        :param int state: Execution state. See ndscheduler.constants.EXECUTION_*
        """
        execution = {
            'eid': execution_id,
            'job_id': job_id,
            'state': state
        }
        execution.update(kwargs)
        execution_insert = self.executions_table.insert().values(**execution)
        with self.engine.begin() as conn:
            conn.execute(execution_insert)

    def get_execution(self, execution_id):
        """Returns execution dict.
        :param str execution_id: Execution id.
        :return: Diction for execution info.
        :rtype: dict
        """
        selectable = select('*').where(self.executions_table.c.eid == execution_id)
        with self.engine.connect() as conn:
            rows = conn.execute(selectable)
            for row in rows:
                return self._build_execution(row)

    def update_execution(self, execution_id, **kwargs):
        """Update execution in database.
        :param str execution_id: Execution id.
        :param kwargs: Keyword arguments.
        """
        execution_update = self.executions_table.update().where(
            self.executions_table.c.eid == execution_id).values(**kwargs)
        with self.engine.begin() as conn:
            conn.execute(execution_update)

    def _build_execution(self, row):
        """Return job execution info from a row of scheduler_execution table.
        :param obj row: A row instance of scheduler_execution table.
        :return: A dictionary of job execution info.
        :rtype: dict
        """
        return_json = {
            'execution_id': row.eid,
            'state': constants.EXECUTION_STATUS_DICT[row.state],
            'hostname': row.hostname,
            'pid': row.pid,
            'task_id': row.task_id,
            'description': row.description,
            'result': row.result,
            'scheduled_time': self.get_time_isoformat_from_db(row.scheduled_time),
            'updated_time': self.get_time_isoformat_from_db(row.updated_time)}
        job = self.lookup_job(row.job_id)
        if job:
            return_json['job'] = {
                'job_id': job.id,
                'name': job.name,
                'task_name': utils.get_job_name(job),
                'pub_args': utils.get_job_args(job)}
            return_json['job'].update(utils.get_cron_strings(job))
        return return_json

    def get_time_isoformat_from_db(self, time_object):
        """Convert time object from database to iso 8601 format.
        :param object time_object: a time object from database, which is different on different
            databases. Subclass of this class for specific database has to override this function.
        :return: iso8601 format string
        :rtype: str
        """
        return time_object.isoformat()

    def get_executions(self, time_range_start, time_range_end):
        """Returns info for multiple job executions.
        :param str time_range_start: ISO format for time range starting point.
        :param str time_range_end: ISO for time range ending point.
        :return: A dictionary of multiple execution info, e.g.,
            {
                'executions': [...]
            }
            Sorted by updated_time.
        :rtype: dict
        """
        utc = dateutil.tz.gettz('UTC')
        start_time = dateutil.parser.parse(time_range_start).replace(tzinfo=utc)
        end_time = dateutil.parser.parse(time_range_end).replace(tzinfo=utc)
        selectable = select('*').where(
            self.executions_table.c.scheduled_time.between(
                start_time, end_time)).order_by(desc(self.executions_table.c.updated_time))

        with self.engine.connect() as conn:
            rows = conn.execute(selectable)
            return_json = {
                'executions': [self._build_execution(row) for row in rows]}

        return return_json

    def add_audit_log(self, job_id, job_name, event, **kwargs):
        """Insert an audit log.
        :param str job_id: string for job id.
        :param str job_name: string for job name.
        :param int event: integer for an event.
        """
        audit_log = {
            'job_id': job_id,
            'job_name': job_name,
            'event': event
        }
        audit_log.update(kwargs)
        log_insert = self.auditlogs_table.insert().values(**audit_log)
        with self.engine.begin() as conn:
            conn.execute(log_insert)

    def get_audit_logs(self, time_range_start, time_range_end):
        """Returns a list of audit logs.
        :param str time_range_start: ISO format for time range starting point.
        :param str time_range_end: ISO for time range ending point.
        :return: A dictionary of multiple audit logs, e.g.,
            {
                'logs': [
                    {
                        'job_id': ...
                        'event': ...
                        'user': ...
                        'description': ...
                    }
                ]
            }
            Sorted by created_time.
        :rtype: dict
        """
        utc = dateutil.tz.gettz('UTC')
        start_time = dateutil.parser.parse(time_range_start).replace(tzinfo=utc)
        end_time = dateutil.parser.parse(time_range_end).replace(tzinfo=utc)
        selectable = select('*').where(
            self.auditlogs_table.c.created_time.between(
                start_time, end_time)).order_by(desc(self.auditlogs_table.c.created_time))

        with self.engine.connect() as conn:
            rows = conn.execute(selectable)
            return_json = {
                'logs': [self._build_audit_log(row) for row in rows]}

        return return_json

    def _build_audit_log(self, row):
        """Return audit_log from a row of scheduler_auditlog table.
        :param obj row: A row instance of scheduler_auditlog table.
        :return: A dictionary of audit log.
        :rtype: dict
        """
        return_dict = {
            'job_id': row.job_id,
            'job_name': row.job_name,
            'event': constants.AUDIT_LOG_DICT[row.event],
            'user': row.user,
            'created_time': self.get_time_isoformat_from_db(row.created_time),
            'description': row.description}
        return return_dict
