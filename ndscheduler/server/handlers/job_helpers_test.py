"""Unit tests for job_helpers module.

These tests are pure-function tests (no tornado / no scheduler needed),
which is the whole point of extracting the logic out of the handler.
"""

import unittest
from unittest import mock

import tornado.web

from ndscheduler.server.handlers import job_helpers


class BuildJobDictTest(unittest.TestCase):
    """Tests for build_job_dict."""

    def _make_job(self, next_run_time='2026-01-01T00:00:00+00:00'):
        """Build a mock apscheduler Job."""
        job = mock.MagicMock()
        job.id = 'abc123'
        job.name = 'Test Job'
        if next_run_time:
            job.next_run_time.isoformat.return_value = next_run_time
        else:
            job.next_run_time = None
        # args layout: [job_class_string, ..., pub_args...]
        job.args = ['my.module.MyJob', 'x', 'y', 'z', 'w', 'arg1', 'arg2']
        job.kwargs = {}

        # Mock trigger fields for get_cron_strings
        trigger = mock.MagicMock()
        trigger.fields = [None, '*', '*', '*', '*', '*', '*/5']  # month..minute
        job.trigger = trigger
        return job

    def test_build_job_dict_with_next_run_time(self):
        job = self._make_job()
        result = job_helpers.build_job_dict(job)

        self.assertEqual(result['job_id'], 'abc123')
        self.assertEqual(result['name'], 'Test Job')
        self.assertEqual(result['next_run_time'], '2026-01-01T00:00:00+00:00')
        self.assertEqual(result['job_class_string'], 'my.module.MyJob')
        self.assertEqual(result['pub_args'], ['arg1', 'arg2'])
        self.assertIn('minute', result)

    def test_build_job_dict_without_next_run_time(self):
        job = self._make_job(next_run_time=None)
        result = job_helpers.build_job_dict(job)
        self.assertEqual(result['next_run_time'], '')


class GenerateModifyDescriptionTest(unittest.TestCase):
    """Tests for generate_modify_description."""

    def test_no_changes_returns_empty(self):
        old = {'name': 'A', 'job_class_string': 'X', 'pub_args': [],
               'minute': '*', 'hour': '*', 'day': '*', 'month': '*', 'day_of_week': '*'}
        new = dict(old)
        self.assertEqual(job_helpers.generate_modify_description(old, new), '')

    def test_name_change_is_captured(self):
        old = {'name': 'Before', 'job_class_string': 'X', 'pub_args': [],
               'minute': '*', 'hour': '*', 'day': '*', 'month': '*', 'day_of_week': '*'}
        new = dict(old)
        new['name'] = 'After'
        desc = job_helpers.generate_modify_description(old, new)
        self.assertIn('Before', desc)
        self.assertIn('After', desc)
        self.assertIn('name', desc)

    def test_multiple_changes_all_captured(self):
        old = {'name': 'A', 'job_class_string': 'X', 'pub_args': [1],
               'minute': '*/5', 'hour': '*', 'day': '*', 'month': '*', 'day_of_week': '*'}
        new = {'name': 'B', 'job_class_string': 'Y', 'pub_args': [2],
               'minute': '*/10', 'hour': '*', 'day': '*', 'month': '*', 'day_of_week': '*'}
        desc = job_helpers.generate_modify_description(old, new)
        self.assertIn('name', desc)
        self.assertIn('job_class_string', desc)
        self.assertIn('pub_args', desc)
        self.assertIn('minute', desc)

    def test_missing_keys_handled_gracefully(self):
        """If a key is missing from either dict, get() returns None and diff still works."""
        old = {'name': 'A'}
        new = {'name': 'A'}
        desc = job_helpers.generate_modify_description(old, new)
        self.assertEqual(desc, '')


class ValidateJobPayloadTest(unittest.TestCase):
    """Tests for validate_job_payload."""

    def test_valid_payload_passes(self):
        payload = {
            'name': 'test',
            'job_class_string': 'my.module.MyJob',
            'minute': '*/5',
        }
        # Should not raise
        job_helpers.validate_job_payload(payload)

    def test_none_payload_raises(self):
        with self.assertRaises(tornado.web.HTTPError) as ctx:
            job_helpers.validate_job_payload(None)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_missing_name_raises(self):
        payload = {'job_class_string': 'my.module.MyJob', 'minute': '*/5'}
        with self.assertRaises(tornado.web.HTTPError) as ctx:
            job_helpers.validate_job_payload(payload)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn('name', ctx.exception.reason)

    def test_missing_job_class_string_raises(self):
        payload = {'name': 'test', 'minute': '*/5'}
        with self.assertRaises(tornado.web.HTTPError) as ctx:
            job_helpers.validate_job_payload(payload)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn('job_class_string', ctx.exception.reason)

    def test_no_cron_fields_raises(self):
        payload = {'name': 'test', 'job_class_string': 'my.module.MyJob'}
        with self.assertRaises(tornado.web.HTTPError) as ctx:
            job_helpers.validate_job_payload(payload)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn('at least one', ctx.exception.reason)

    def test_any_single_cron_field_suffices(self):
        for cron_field in ('month', 'day', 'hour', 'minute', 'day_of_week'):
            payload = {
                'name': 'test',
                'job_class_string': 'my.module.MyJob',
                cron_field: '*',
            }
            # Should not raise
            job_helpers.validate_job_payload(payload)

    def test_non_dict_payload_raises(self):
        with self.assertRaises(tornado.web.HTTPError):
            job_helpers.validate_job_payload('not a dict')


class GetJobOr404Test(unittest.TestCase):
    """Tests for get_job_or_404."""

    def test_returns_job_when_found(self):
        mock_manager = mock.MagicMock()
        fake_job = mock.MagicMock()
        mock_manager.get_job.return_value = fake_job

        result = job_helpers.get_job_or_404(mock_manager, 'good-id')
        self.assertIs(result, fake_job)

    def test_raises_400_when_not_found(self):
        mock_manager = mock.MagicMock()
        mock_manager.get_job.return_value = None

        with self.assertRaises(tornado.web.HTTPError) as ctx:
            job_helpers.get_job_or_404(mock_manager, 'bad-id')
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn('bad-id', ctx.exception.reason)


if __name__ == '__main__':
    unittest.main()
