"""Handler for jobs endpoint.

Every HTTP verb maps to a single *blocking* operation (``_get_jobs``,
``_add_job``, ``_delete_job`` ...) that returns the response body as a dict.
:meth:`base.BaseHandler.respond_async` runs that operation off the IOLoop --
or inline for ``?sync=...`` requests -- finishes the response with its result
and, crucially, turns any failure into a proper HTTP error response instead of
an unhandled exception raised *after* the handler has already returned.

Job-shaped logic -- building the response dict, diffing a modification for the
audit log, validating the request payload, the "job not found" check -- lives
in :mod:`ndscheduler.server.handlers.job_helpers`, so adding a field or a rule
only touches that module.
"""

import json

import tornado.web

from ndscheduler.corescheduler import constants
from ndscheduler.server.handlers import base
from ndscheduler.server.handlers import job_helpers


class Handler(base.BaseHandler):
    """Handles ``/api/v1/jobs`` and ``/api/v1/jobs/{job_id}``."""

    # ------------------------------------------------------------------ #
    # Blocking operations                                                  #
    #                                                                      #
    # Each returns the response body (a dict) and may raise an HTTPError   #
    # (e.g. via job_helpers.get_job_or_404). They are never called         #
    # directly -- always through self.respond_async().                     #
    # ------------------------------------------------------------------ #

    def _get_jobs(self):
        """Returns ``{'jobs': [...]}`` for every scheduled job."""
        jobs = self.scheduler_manager.get_jobs()
        return {'jobs': [job_helpers.build_job_dict(job) for job in jobs]}

    def _get_job(self, job_id):
        """Returns the job dict for ``job_id`` (HTTP 400 if it is missing)."""
        job = job_helpers.get_job_or_404(self.scheduler_manager, job_id)
        return job_helpers.build_job_dict(job)

    def _add_job(self):
        """Adds a job and records an audit log.

        :return: ``{'job_id': <new job id>}`` with a 201 status.
        :rtype: dict
        """
        job_id = self.scheduler_manager.add_job(**self.json_args)
        self.record_audit_log(job_id, self.json_args['name'], constants.AUDIT_LOG_ADDED)
        self.set_status(201)
        return {'job_id': job_id}

    def _delete_job(self, job_id):
        """Deletes a job and records an audit log with its last known state.

        :return: ``{'job_id': job_id}``.
        :rtype: dict
        """
        job = self._get_job(job_id)
        self.scheduler_manager.remove_job(job_id)
        self.record_audit_log(job_id, job['name'], constants.AUDIT_LOG_DELETED,
                              description=json.dumps(job))
        return {'job_id': job_id}

    def _modify_job(self, job_id):
        """Modifies a job and records an audit log describing the diff.

        :return: ``{'job_id': job_id}``.
        :rtype: dict
        """
        old_job = self._get_job(job_id)
        self.scheduler_manager.modify_job(job_id, **self.json_args)
        new_job = self._get_job(job_id)
        self.record_audit_log(
            job_id, new_job['name'], constants.AUDIT_LOG_MODIFIED,
            description=job_helpers.generate_modify_description(old_job, new_job))
        return {'job_id': job_id}

    def _pause_job(self, job_id):
        """Pauses a job and records an audit log.

        :return: ``{'job_id': job_id}``.
        :rtype: dict
        """
        job = job_helpers.get_job_or_404(self.scheduler_manager, job_id)
        self.scheduler_manager.pause_job(job_id)
        self.record_audit_log(job_id, job.name, constants.AUDIT_LOG_PAUSED)
        return {'job_id': job_id}

    def _resume_job(self, job_id):
        """Resumes a paused job and records an audit log.

        :return: ``{'job_id': job_id}``.
        :rtype: dict
        """
        job = job_helpers.get_job_or_404(self.scheduler_manager, job_id)
        self.scheduler_manager.resume_job(job_id)
        self.record_audit_log(job_id, job.name, constants.AUDIT_LOG_RESUMED)
        return {'job_id': job_id}

    # ------------------------------------------------------------------ #
    # HTTP verb handlers                                                   #
    # ------------------------------------------------------------------ #

    @tornado.web.removeslash
    @tornado.web.asynchronous
    def get(self, job_id=None):
        """GET ``/api/v1/jobs`` (list) or ``/api/v1/jobs/{job_id}`` (one)."""
        if job_id is None:
            self.respond_async(self._get_jobs)
        else:
            self.respond_async(self._get_job, job_id)

    @tornado.web.removeslash
    @tornado.web.asynchronous
    def post(self):
        """POST ``/api/v1/jobs`` -- adds a job."""
        job_helpers.validate_job_payload(self.json_args)
        self.respond_async(self._add_job)

    @tornado.web.removeslash
    @tornado.web.asynchronous
    def delete(self, job_id):
        """DELETE ``/api/v1/jobs/{job_id}`` -- deletes a job."""
        self.respond_async(self._delete_job, job_id)

    @tornado.web.removeslash
    @tornado.web.asynchronous
    def put(self, job_id):
        """PUT ``/api/v1/jobs/{job_id}`` -- modifies a job."""
        job_helpers.validate_job_payload(self.json_args)
        self.respond_async(self._modify_job, job_id)

    @tornado.web.removeslash
    @tornado.web.asynchronous
    def patch(self, job_id):
        """PATCH ``/api/v1/jobs/{job_id}`` -- pauses a job."""
        self.respond_async(self._pause_job, job_id)

    @tornado.web.removeslash
    @tornado.web.asynchronous
    def options(self, job_id):
        """OPTIONS ``/api/v1/jobs/{job_id}`` -- resumes a paused job."""
        self.respond_async(self._resume_job, job_id)
