"""Unit tests for executions endpoint.

``?sync=true`` runs the handler's blocking operation inline (see
``BaseHandler.respond_async``), which is deterministic and avoids sharing the
in-memory SQLite datastore across threads.
"""

import datetime
import json

import tornado.testing

from ndscheduler.corescheduler import constants
from ndscheduler.corescheduler import scheduler_manager
from ndscheduler.server import server
from ndscheduler.server.handlers import executions  # noqa: F401  (validate import path)


class ExecutionsTest(tornado.testing.AsyncHTTPTestCase):

    def setUp(self, *args, **kwargs):
        super(ExecutionsTest, self).setUp(*args, **kwargs)
        self.server.start_scheduler()
        self.EXECUTIONS_URL = '/api/v1/executions'

    def tearDown(self, *args, **kwargs):
        self.server.stop_scheduler()
        super(ExecutionsTest, self).tearDown(*args, **kwargs)

    def get_app(self):
        # Shouldn't use singleton here. Or the test will reuse IOLoop and cause
        #   RuntimeError: IOLoop is closing
        scp = 'ndscheduler.corescheduler.core.base.BaseScheduler'
        dcp = 'ndscheduler.corescheduler.datastore.providers.sqlite.DatastoreSqlite'
        self.scheduler = scheduler_manager.SchedulerManager(
            scheduler_class_path=scp,
            datastore_class_path=dcp
        )
        self.server = server.SchedulerServer(self.scheduler)
        return self.server.application

    def test_get_execution(self):
        datastore = self.scheduler.get_datastore()
        execution1 = {
            'eid': '1234',
            'job_id': '5678',
            'state': constants.EXECUTION_STATUS_SCHEDULED
        }
        datastore.add_execution(execution1['eid'], execution1['job_id'], execution1['state'])
        response = self.fetch(self.EXECUTIONS_URL + '/%s?sync=true' % execution1['eid'])
        return_info = json.loads(response.body.decode())
        self.assertEqual(return_info['execution_id'], execution1['eid'])
        self.assertEqual(return_info['state'],
                         constants.EXECUTION_STATUS_DICT[execution1['state']])

    def test_get_executions(self):
        datastore = self.scheduler.get_datastore()
        execution1 = {
            'eid': '1234',
            'job_id': '5678',
            'state': constants.EXECUTION_STATUS_SCHEDULED,
            'scheduled_time': datetime.datetime.utcnow()
        }
        datastore.add_execution(execution1['eid'], execution1['job_id'], execution1['state'],
                                scheduled_time=execution1['scheduled_time'])
        two_minutes_later = execution1['scheduled_time'] + datetime.timedelta(minutes=2)
        response = self.fetch(self.EXECUTIONS_URL + '?sync=true&time_range_end=%s' % (
            two_minutes_later.isoformat()))
        return_info = json.loads(response.body.decode())
        self.assertEqual(return_info['executions'][0]['execution_id'], execution1['eid'])

    def test_get_execution_not_found(self):
        """GET a non-existent execution returns 400 with a JSON error body."""
        response = self.fetch(self.EXECUTIONS_URL + '/nonexistent-id?sync=true')
        self.assertEqual(response.code, 400)
        return_info = json.loads(response.body.decode())
        self.assertIn('error', return_info)
        self.assertIn('nonexistent-id', return_info['error'])
