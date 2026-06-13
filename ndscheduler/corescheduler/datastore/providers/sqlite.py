"""Represents SQLite datastore."""

import datetime

import pytz

from ndscheduler.corescheduler.datastore import base
from ndscheduler.corescheduler.exceptions import DatastoreConfigError


class DatastoreSqlite(base.DatastoreBase):

    # SQLite needs no connection keys: None / empty dict yields an in-memory
    # database (see ``get_db_url``). Declared explicitly so the "no required
    # config" contract is obvious alongside the other providers.
    REQUIRED_CONFIG_KEYS = ()

    @classmethod
    def validate_config(cls, db_config):
        """SQLite accepts ``None`` / an empty dict (in-memory) or a dict with
        an optional string ``file_path``.

        The shared base check enforces the dict-or-None rule; here we add the
        one sqlite-specific rule (``file_path`` must be a string) on top.
        """
        super(DatastoreSqlite, cls).validate_config(db_config)
        if (isinstance(db_config, dict) and 'file_path' in db_config
                and not isinstance(db_config['file_path'], str)):
            raise DatastoreConfigError(
                "DatastoreSqlite: 'file_path' must be a string, got %r"
                % (db_config['file_path'],))

    def get_db_url(self):
        """Returns the db url to establish a SQLite connection, where db_config is passed in
        on initialization as:
        {
            'file_path': 'an_absolute_file_path'
        }
        If 'file_path' is not passed in, an in-memory SQLite db is created.
        :return: string db url
        """
        file_path = ''
        if self.db_config and 'file_path' in self.db_config:
            file_path = self.db_config['file_path']
        return 'sqlite:///' + file_path

    def get_time_isoformat_from_db(self, time_object):
        date = datetime.datetime.strptime(time_object, '%Y-%m-%d %H:%M:%S.%f')
        date = pytz.utc.localize(date)
        return date.isoformat()
