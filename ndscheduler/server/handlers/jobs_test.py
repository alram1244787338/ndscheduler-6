"""Unit tests for jobs endpoint.

These drive the real handler code path: ``?sync=true`` makes
``BaseHandler.respond_async`` run the blocking operation inline on the IOLoop
thread (instead of the thread pool), which is both deterministic and required
here because the in-memory SQLite datastore cannot be shared across threads.
"""

import json

from datetime import datetime
from datetime import timedelta

import tornado.testing

from ndscheduler.corescheduler import scheduler_manager
from ndscheduler.corescheduler import utils
from ndscheduler.server import server
from ndscheduler.server.handlers import jobs  # noqa: F401  (ensures handler import path is valid)


class JobsTest(tornado.testing.AsyncHTTPTestCase):

    JSON_HEADERS = {'Content-Type': 'application/json; charset=UTF-8'}

    def setUp(self, *args, **kwargs):
        super(JobsTest, self).setUp(*args, **kwargs)
        self.server.start_scheduler()
        self.JOBS_URL = '/api/v1/jobs'

    def tearDown(self, *args, **kwargs):
        self.server.stop_scheduler()
        super(JobsTest, self).tearDown(*args, **kwargs)

    def get_app(self):
        """This is required by tornado.testing."""
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

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #

    def _add_job(self, **overrides):
        """POSTs a valid job and returns its job_id."""
        data = {
            'job_class_string': 'hello.world',
            'name': 'hello world job',
            'minute': '*/5'}
        data.update(overrides)
        response = self.fetch(self.JOBS_URL + '?sync=true', method='POST',
                              headers=self.JSON_HEADERS, body=json.dumps(data))
        self.assertEqual(response.code, 201)
        return json.loads(response.body.decode())['job_id']

    # ------------------------------------------------------------------ #
    # Happy paths                                                          #
    # ------------------------------------------------------------------ #

    def test_add_job_success(self):
        data = {
            'job_class_string': 'hello.world',
            'name': 'hello world job',
            'minute': '*/5'}
        response = self.fetch(self.JOBS_URL + '?sync=true', method='POST',
                              headers=self.JSON_HEADERS, body=json.dumps(data))
        self.assertEqual(response.code, 201)
        return_info = json.loads(response.body.decode())
        self.assertTrue('job_id' in return_info)
        self.assertEqual(len(return_info['job_id']), 32)
        job = self.scheduler.get_job(return_info['job_id'])
        self.assertEqual(job.name, data['name'])

    def test_add_job_failed(self):
        # Missing a cron field.
        data = {
            'job_class_string': 'hello.world',
            'name': 'hello world job'}
        response = self.fetch(self.JOBS_URL + '?sync=true', method='POST',
                              headers=self.JSON_HEADERS, body=json.dumps(data))
        self.assertEqual(response.code, 400)

        # Missing the name.
        data = {
            'job_class_string': 'hello.world',
            'minute': '*/5'}
        response = self.fetch(self.JOBS_URL + '?sync=true', method='POST',
                              headers=self.JSON_HEADERS, body=json.dumps(data))
        self.assertEqual(response.code, 400)

    def test_pause_resume_job(self):
        job_id = self._add_job()

        response = self.fetch(self.JOBS_URL + '/' + job_id + '?sync=true',
                              method='PATCH', body='{}')
        self.assertEqual(response.code, 200)

        response = self.fetch(self.JOBS_URL + '/' + job_id + '?sync=true', method='OPTIONS')
        self.assertEqual(response.code, 200)

    def test_get_jobs(self):
        data = {
            'job_class_string': 'hello.world',
            'name': 'hello world job',
            'minute': '*/5'}
        self._add_job(**data)

        response = self.fetch(self.JOBS_URL + '?sync=true')
        return_info = json.loads(response.body.decode())
        self.assertEqual(len(return_info['jobs']), 1)
        job = return_info['jobs'][0]
        self.assertEqual(job['job_class_string'], data['job_class_string'])
        self.assertEqual(job['name'], data['name'])
        self.assertEqual(job['minute'], data['minute'])

    def test_get_job(self):
        job_id = self._add_job(name='single job')

        response = self.fetch(self.JOBS_URL + '/' + job_id + '?sync=true')
        self.assertEqual(response.code, 200)
        return_info = json.loads(response.body.decode())
        self.assertEqual(return_info['job_id'], job_id)
        self.assertEqual(return_info['name'], 'single job')

    def test_delete_job(self):
        job_id = self._add_job()

        response = self.fetch(self.JOBS_URL + '/' + job_id + '?sync=true', method='DELETE')
        self.assertEqual(response.code, 200)

        response = self.fetch(self.JOBS_URL + '?sync=true')
        return_info = json.loads(response.body.decode())
        self.assertEqual(len(return_info['jobs']), 0)

    def test_modify_job(self):
        job_id = self._add_job()
        job = self.scheduler.get_job(job_id)
        self.assertEqual(utils.get_job_name(job), 'hello.world')

        data = {
            'job_class_string': 'hello.world!!!!',
            'name': 'hello world job~~~~',
            'minute': '*/20'}
        response = self.fetch(self.JOBS_URL + '/' + job_id + '?sync=true',
                              method='PUT', headers=self.JSON_HEADERS, body=json.dumps(data))
        self.assertEqual(response.code, 200)
        job = self.scheduler.get_job(job_id)
        self.assertEqual(utils.get_job_name(job), data['job_class_string'])
        self.assertEqual(job.name, data['name'])

    # ------------------------------------------------------------------ #
    # Edge cases                                                           #
    # ------------------------------------------------------------------ #

    def test_get_job_not_found(self):
        """GET a non-existent job returns 400 with a JSON error body."""
        response = self.fetch(self.JOBS_URL + '/nonexistent-id?sync=true')
        self.assertEqual(response.code, 400)
        return_info = json.loads(response.body.decode())
        self.assertIn('error', return_info)
        self.assertIn('nonexistent-id', return_info['error'])

    def test_delete_job_not_found(self):
        """DELETE a non-existent job returns 400 (not a stray 200 + crash)."""
        response = self.fetch(self.JOBS_URL + '/nonexistent-id?sync=true', method='DELETE')
        self.assertEqual(response.code, 400)
        return_info = json.loads(response.body.decode())
        self.assertIn('error', return_info)
        self.assertIn('nonexistent-id', return_info['error'])

    def test_modify_job_not_found(self):
        """PUT a non-existent job returns 400."""
        data = {
            'job_class_string': 'hello.world',
            'name': 'test',
            'minute': '*/5'}
        response = self.fetch(self.JOBS_URL + '/nonexistent-id?sync=true',
                              method='PUT', headers=self.JSON_HEADERS, body=json.dumps(data))
        self.assertEqual(response.code, 400)
        return_info = json.loads(response.body.decode())
        self.assertIn('error', return_info)

    def test_pause_job_not_found(self):
        """PATCH a non-existent job returns 400 instead of raising in the background."""
        response = self.fetch(self.JOBS_URL + '/nonexistent-id?sync=true',
                              method='PATCH', body='{}')
        self.assertEqual(response.code, 400)

    def test_add_job_missing_name(self):
        data = {'job_class_string': 'hello.world', 'minute': '*/5'}
        response = self.fetch(self.JOBS_URL + '?sync=true', method='POST',
                              headers=self.JSON_HEADERS, body=json.dumps(data))
        self.assertEqual(response.code, 400)
        return_info = json.loads(response.body.decode())
        self.assertIn('error', return_info)
        self.assertIn('name', return_info['error'])

    def test_add_job_missing_job_class_string(self):
        data = {'name': 'test job', 'minute': '*/5'}
        response = self.fetch(self.JOBS_URL + '?sync=true', method='POST',
                              headers=self.JSON_HEADERS, body=json.dumps(data))
        self.assertEqual(response.code, 400)
        return_info = json.loads(response.body.decode())
        self.assertIn('error', return_info)
        self.assertIn('job_class_string', return_info['error'])

    def test_add_job_no_cron_fields(self):
        data = {'name': 'test job', 'job_class_string': 'hello.world'}
        response = self.fetch(self.JOBS_URL + '?sync=true', method='POST',
                              headers=self.JSON_HEADERS, body=json.dumps(data))
        self.assertEqual(response.code, 400)
        return_info = json.loads(response.body.decode())
        self.assertIn('error', return_info)
        self.assertIn('at least one', return_info['error'])

    def test_add_job_invalid_json(self):
        """A body declared as JSON but malformed returns a clean 400."""
        response = self.fetch(self.JOBS_URL + '?sync=true', method='POST',
                              headers=self.JSON_HEADERS, body='{not valid json')
        self.assertEqual(response.code, 400)

    def test_modify_job_audit_description(self):
        """Modifying a job writes a 'modified' audit log whose description diffs the change."""
        job_id = self._add_job(name='original name', minute='*/5')

        data = {
            'job_class_string': 'hello.world',
            'name': 'modified name',
            'minute': '*/10'}
        response = self.fetch(self.JOBS_URL + '/' + job_id + '?sync=true',
                              method='PUT', headers=self.JSON_HEADERS, body=json.dumps(data))
        self.assertEqual(response.code, 200)

        datastore = self.scheduler.get_datastore()
        now = datetime.utcnow()
        logs = datastore.get_audit_logs(
            (now - timedelta(minutes=10)).isoformat(), now.isoformat())
        modify_logs = [entry for entry in logs['logs'] if entry['event'] == 'modified']
        self.assertTrue(len(modify_logs) > 0)
        description = modify_logs[0]['description']
        self.assertIn('original name', description)
        self.assertIn('modified name', description)
