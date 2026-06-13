"""Handler for executions endpoint.

  * GET    /api/v1/executions            -- list executions in a time window
  * GET    /api/v1/executions/{eid}      -- get a single execution
  * POST   /api/v1/executions/{job_id}   -- manually run a job (new execution)
  * DELETE /api/v1/executions/{job_id}   -- stop an execution (not implemented)

Like the jobs handler, each verb maps to a single blocking operation that
returns the response body and is dispatched through
:meth:`base.BaseHandler.respond_async`.
"""

import tornado.web

from ndscheduler import settings
from ndscheduler.corescheduler import constants
from ndscheduler.corescheduler import utils
from ndscheduler.server.handlers import base


class Handler(base.BaseHandler):
    """Handles ``/api/v1/executions`` and ``/api/v1/executions/{id}``."""

    # ------------------------------------------------------------------ #
    # Blocking operations                                                  #
    # ------------------------------------------------------------------ #

    def _get_execution(self, execution_id):
        """Returns the execution dict for ``execution_id``.

        :raises tornado.web.HTTPError: 400 if the execution does not exist.
        :rtype: dict
        """
        execution = self.datastore.get_execution(execution_id)
        if not execution:
            raise tornado.web.HTTPError(400, reason='Execution not found: %s' % execution_id)
        return execution

    def _get_executions(self):
        """Returns the executions within the requested time window.

        :rtype: dict
        """
        time_range_start, time_range_end = self.get_time_range_args()
        return self.datastore.get_executions(time_range_start, time_range_end)

    def _run_job(self, job_id):
        """Kicks off a manual run of a job and records an audit log.

        :raises tornado.web.HTTPError: 400 if the job does not exist.
        :return: ``{'execution_id': <new execution id>}``.
        :rtype: dict
        """
        job = self.scheduler_manager.get_job(job_id)
        if not job:
            raise tornado.web.HTTPError(400, reason='Job not found: %s' % job_id)

        job_name = utils.get_job_name(job)
        args = utils.get_job_args(job)
        kwargs = job.kwargs

        scheduler_class = utils.import_from_path(settings.SCHEDULER_CLASS)
        execution_id = scheduler_class.run_job(
            job_name, job_id, settings.DATABASE_CLASS,
            self.datastore.db_config, self.datastore.table_names,
            *args, **kwargs)

        self.record_audit_log(job_id, job.name, constants.AUDIT_LOG_CUSTOM_RUN,
                              description=execution_id)
        return {'execution_id': execution_id}

    # ------------------------------------------------------------------ #
    # HTTP verb handlers                                                   #
    # ------------------------------------------------------------------ #

    @tornado.web.removeslash
    @tornado.web.asynchronous
    def get(self, execution_id=None):
        """GET ``/api/v1/executions`` (list) or ``.../{execution_id}`` (one).

        For the list endpoint, ``time_range_start`` / ``time_range_end`` query
        arguments bound the window (defaulting to the last 10 minutes).
        """
        if execution_id is None:
            self.respond_async(self._get_executions)
        else:
            self.respond_async(self._get_execution, execution_id)

    @tornado.web.removeslash
    @tornado.web.asynchronous
    def post(self, job_id):
        """POST ``/api/v1/executions/{job_id}`` -- manually runs a job."""
        self.respond_async(self._run_job, job_id)

    @tornado.web.removeslash
    def delete(self, job_id):
        """DELETE ``/api/v1/executions/{job_id}`` -- stop a run (unimplemented)."""
        raise tornado.web.HTTPError(501, reason='Not implemented yet.')
