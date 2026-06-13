"""Tests for the datastore factory, provider validation, and
SchedulerManager input validation.

Covers:
- The happy-path / default-startup flow (sqlite in-memory).
- Table-name resolution (defaults, overrides, unknown keys).
- Provider-level config validation for mysql / postgres / sqlite.
- SchedulerManager-level input validation.
- Bad provider class paths.
"""

import unittest

from apscheduler.schedulers.blocking import BlockingScheduler

from ndscheduler.corescheduler import constants
from ndscheduler.corescheduler import scheduler_manager
from ndscheduler.corescheduler.datastore import factory as datastore_factory
from ndscheduler.corescheduler.datastore.providers.mysql import DatastoreMySQL
from ndscheduler.corescheduler.datastore.providers.postgres import DatastorePostgres
from ndscheduler.corescheduler.datastore.providers.sqlite import DatastoreSqlite
from ndscheduler.corescheduler.exceptions import (
    DatastoreConfigError,
    DatastoreInitError,
    SchedulerConfigError,
)


# ---------------------------------------------------------------------------
# Table-name resolution
# ---------------------------------------------------------------------------

class ResolveTableNamesTest(unittest.TestCase):

    def test_defaults_when_none(self):
        result = datastore_factory.resolve_table_names(None)
        self.assertEqual(result['jobs_tablename'], constants.DEFAULT_JOBS_TABLENAME)
        self.assertEqual(result['executions_tablename'], constants.DEFAULT_EXECUTIONS_TABLENAME)
        self.assertEqual(result['auditlogs_tablename'], constants.DEFAULT_AUDIT_LOGS_TABLENAME)

    def test_defaults_when_empty_dict(self):
        result = datastore_factory.resolve_table_names({})
        self.assertEqual(result['jobs_tablename'], constants.DEFAULT_JOBS_TABLENAME)

    def test_overrides_applied(self):
        result = datastore_factory.resolve_table_names({
            'jobs_tablename': 'my_jobs',
        })
        self.assertEqual(result['jobs_tablename'], 'my_jobs')
        # Other keys still get defaults.
        self.assertEqual(result['executions_tablename'], constants.DEFAULT_EXECUTIONS_TABLENAME)

    def test_unknown_keys_rejected(self):
        with self.assertRaises(DatastoreConfigError) as ctx:
            datastore_factory.resolve_table_names({'typo_tablename': 'x'})
        self.assertIn('typo_tablename', str(ctx.exception))

    def test_non_dict_rejected(self):
        with self.assertRaises(DatastoreConfigError):
            datastore_factory.resolve_table_names('not_a_dict')


# ---------------------------------------------------------------------------
# Provider-level config validation
# ---------------------------------------------------------------------------

class SqliteValidateConfigTest(unittest.TestCase):

    def test_none_is_valid(self):
        DatastoreSqlite.validate_config(None)  # should not raise

    def test_empty_dict_is_valid(self):
        DatastoreSqlite.validate_config({})

    def test_file_path_string_is_valid(self):
        DatastoreSqlite.validate_config({'file_path': '/tmp/test.db'})

    def test_non_dict_rejected(self):
        with self.assertRaises(DatastoreConfigError):
            DatastoreSqlite.validate_config('sqlite:///foo.db')

    def test_non_string_file_path_rejected(self):
        with self.assertRaises(DatastoreConfigError):
            DatastoreSqlite.validate_config({'file_path': 12345})


class MySQLValidateConfigTest(unittest.TestCase):

    VALID = {
        'user': 'u', 'password': 'p', 'hostname': 'h',
        'port': 3306, 'database': 'db',
    }

    def test_valid_config(self):
        DatastoreMySQL.validate_config(self.VALID)  # should not raise

    def test_none_rejected(self):
        with self.assertRaises(DatastoreConfigError):
            DatastoreMySQL.validate_config(None)

    def test_empty_dict_rejected(self):
        with self.assertRaises(DatastoreConfigError):
            DatastoreMySQL.validate_config({})

    def test_missing_key_rejected(self):
        cfg = dict(self.VALID)
        del cfg['hostname']
        with self.assertRaises(DatastoreConfigError) as ctx:
            DatastoreMySQL.validate_config(cfg)
        self.assertIn('hostname', str(ctx.exception))

    def test_non_int_port_rejected(self):
        cfg = dict(self.VALID)
        cfg['port'] = '3306'
        with self.assertRaises(DatastoreConfigError) as ctx:
            DatastoreMySQL.validate_config(cfg)
        self.assertIn('port', str(ctx.exception))


class PostgresValidateConfigTest(unittest.TestCase):

    VALID = {
        'user': 'u', 'password': 'p', 'hostname': 'h',
        'port': 5432, 'database': 'db', 'sslmode': 'disable',
    }

    def test_valid_config(self):
        DatastorePostgres.validate_config(self.VALID)

    def test_none_rejected(self):
        with self.assertRaises(DatastoreConfigError):
            DatastorePostgres.validate_config(None)

    def test_missing_sslmode_rejected(self):
        cfg = dict(self.VALID)
        del cfg['sslmode']
        with self.assertRaises(DatastoreConfigError) as ctx:
            DatastorePostgres.validate_config(cfg)
        self.assertIn('sslmode', str(ctx.exception))

    def test_non_int_port_rejected(self):
        cfg = dict(self.VALID)
        cfg['port'] = '5432'
        with self.assertRaises(DatastoreConfigError):
            DatastorePostgres.validate_config(cfg)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

class FactoryTest(unittest.TestCase):

    SQLITE_PATH = 'ndscheduler.corescheduler.datastore.providers.sqlite.DatastoreSqlite'

    def setUp(self):
        # Reset the sqlite singleton so tests are independent.
        DatastoreSqlite.destroy_instance()

    def tearDown(self):
        DatastoreSqlite.destroy_instance()

    def test_create_sqlite_default(self):
        store = datastore_factory.create_datastore(self.SQLITE_PATH)
        self.assertIsInstance(store, DatastoreSqlite)
        # Table names should be defaults.
        self.assertEqual(store.table_names['jobs_tablename'],
                         constants.DEFAULT_JOBS_TABLENAME)

    def test_create_sqlite_with_custom_table(self):
        store = datastore_factory.create_datastore(
            self.SQLITE_PATH,
            db_config={'file_path': ''},
            table_names={'jobs_tablename': 'custom_jobs'},
        )
        self.assertEqual(store.table_names['jobs_tablename'], 'custom_jobs')

    def test_bad_class_path_raises(self):
        with self.assertRaises(DatastoreInitError):
            datastore_factory.create_datastore('no.such.module.Class')

    def test_empty_class_path_raises(self):
        with self.assertRaises(DatastoreConfigError):
            datastore_factory.create_datastore('')

    def test_none_class_path_raises(self):
        with self.assertRaises(DatastoreConfigError):
            datastore_factory.create_datastore(None)

    def test_bad_config_for_mysql_raises(self):
        mysql_path = 'ndscheduler.corescheduler.datastore.providers.mysql.DatastoreMySQL'
        with self.assertRaises(DatastoreConfigError):
            datastore_factory.create_datastore(mysql_path, db_config={})


# ---------------------------------------------------------------------------
# SchedulerManager input validation
# ---------------------------------------------------------------------------

class SchedulerManagerValidationTest(unittest.TestCase):

    SCHEDULER_CLASS = 'ndscheduler.corescheduler.core.base.BaseScheduler'
    SQLITE_PATH = 'ndscheduler.corescheduler.datastore.providers.sqlite.DatastoreSqlite'

    def setUp(self):
        DatastoreSqlite.destroy_instance()

    def tearDown(self):
        DatastoreSqlite.destroy_instance()

    def test_default_startup(self):
        """The same invocation the existing tests use must still work."""
        mgr = scheduler_manager.SchedulerManager(
            self.SCHEDULER_CLASS, self.SQLITE_PATH,
        )
        # Datastore should be the default sqlite with default table names.
        ds = mgr.get_datastore()
        self.assertIsInstance(ds, DatastoreSqlite)
        self.assertEqual(ds.table_names['jobs_tablename'],
                         constants.DEFAULT_JOBS_TABLENAME)

    def test_empty_scheduler_class_path_raises(self):
        with self.assertRaises(SchedulerConfigError):
            scheduler_manager.SchedulerManager('', self.SQLITE_PATH)

    def test_empty_datastore_class_path_raises(self):
        with self.assertRaises(SchedulerConfigError):
            scheduler_manager.SchedulerManager(self.SCHEDULER_CLASS, '')

    def test_bad_thread_pool_size_raises(self):
        with self.assertRaises(SchedulerConfigError):
            scheduler_manager.SchedulerManager(
                self.SCHEDULER_CLASS, self.SQLITE_PATH,
                thread_pool_size=0,
            )

    def test_bad_thread_pool_type_raises(self):
        with self.assertRaises(SchedulerConfigError):
            scheduler_manager.SchedulerManager(
                self.SCHEDULER_CLASS, self.SQLITE_PATH,
                thread_pool_size='four',
            )

    def test_bad_job_max_instances_raises(self):
        with self.assertRaises(SchedulerConfigError):
            scheduler_manager.SchedulerManager(
                self.SCHEDULER_CLASS, self.SQLITE_PATH,
                job_max_instances=-1,
            )

    def test_bad_misfire_grace_raises(self):
        with self.assertRaises(SchedulerConfigError):
            scheduler_manager.SchedulerManager(
                self.SCHEDULER_CLASS, self.SQLITE_PATH,
                job_misfire_grace_sec=-1,
            )

    def test_empty_timezone_raises(self):
        with self.assertRaises(SchedulerConfigError):
            scheduler_manager.SchedulerManager(
                self.SCHEDULER_CLASS, self.SQLITE_PATH,
                timezone='',
            )


# ---------------------------------------------------------------------------
# Backward-compat: direct datastore construction still works
# ---------------------------------------------------------------------------

class DirectDatastoreConstructionTest(unittest.TestCase):

    def setUp(self):
        DatastoreSqlite.destroy_instance()

    def tearDown(self):
        DatastoreSqlite.destroy_instance()

    def test_get_instance_no_args(self):
        """The pattern used by base_test.py must still work."""
        store = DatastoreSqlite.get_instance()
        fake_scheduler = BlockingScheduler()
        store.start(fake_scheduler, None)
        self.assertIsInstance(store, DatastoreSqlite)
        # Table names should be populated even though none were passed.
        self.assertIn('jobs_tablename', store.table_names)

    def test_get_instance_with_table_names(self):
        store = DatastoreSqlite.get_instance(
            db_config={'file_path': ''},
            table_names={'jobs_tablename': 'compat_jobs'},
        )
        self.assertEqual(store.table_names['jobs_tablename'], 'compat_jobs')
        # Defaults should still be filled for the other keys.
        self.assertEqual(store.table_names['executions_tablename'],
                         constants.DEFAULT_EXECUTIONS_TABLENAME)


if __name__ == '__main__':
    unittest.main()
