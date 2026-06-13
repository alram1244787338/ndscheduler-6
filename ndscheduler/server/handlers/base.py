"""Base tornado.web.RequestHandler classes.

This package provides a common set of RequestHandler objects to be
subclassed in the rest of the app for different URLs.

It centralizes the patterns that every API handler used to re-implement on its
own, so the concrete handlers describe *what* a request does rather than the
boilerplate of *how* it is dispatched:

  * JSON request body parsing/validation (:meth:`BaseHandler.prepare`).
  * The blocking/non-blocking boundary -- running datastore access off the
    IOLoop and finishing the response with the result, with a guaranteed
    fallback if that background work fails (:meth:`BaseHandler.respond_async`).
  * ``time_range_start`` / ``time_range_end`` query parsing shared by the
    executions and audit-log endpoints (:meth:`BaseHandler.get_time_range_args`).
  * Uniform JSON error bodies, even for uncaught errors
    (:meth:`BaseHandler.write_error`).
  * Best-effort audit-log writes (:meth:`BaseHandler.record_audit_log`).
"""

import json
import logging

from concurrent import futures
from datetime import datetime
from datetime import timedelta

import tornado.concurrent
import tornado.gen
import tornado.web

from ndscheduler import settings

logger = logging.getLogger(__name__)


class BaseHandler(tornado.web.RequestHandler):
    """Common base for all scheduler API handlers.

    Subclasses get:
      * ``self.json_args`` -- parsed JSON body (or ``None``).
      * ``self.username`` -- login user (override :meth:`get_username`).
      * ``self.scheduler_manager`` / ``self.datastore`` -- ready to use.
      * :meth:`respond_async` -- the single blocking/non-blocking boundary.
      * :meth:`get_time_range_args` -- shared time-window query parsing.
      * :meth:`record_audit_log` -- audit-log write that never fails a request.
    """

    executor = futures.ThreadPoolExecutor(max_workers=settings.TORNADO_MAX_WORKERS)

    # ------------------------------------------------------------------ #
    # Request lifecycle                                                    #
    # ------------------------------------------------------------------ #

    def prepare(self):
        """Preprocess requests: parse JSON body, attach shared attributes."""
        self.json_args = self._parse_json_body()

        # For audit log
        self.username = self.get_username()
        self.scheduler_manager = self.application.settings['scheduler_manager']
        self.datastore = self.scheduler_manager.get_datastore()

    def _parse_json_body(self):
        """Decodes a JSON request body.

        :return: the parsed body, or ``None`` when the request carries no JSON.
        :rtype: dict

        :raises tornado.web.HTTPError: 400 if the body is declared as JSON but
            cannot be parsed.
        """
        content_type = self.request.headers.get('Content-Type', '')
        if not content_type.startswith('application/json') or not self.request.body:
            return None
        try:
            return json.loads(self.request.body.decode())
        except ValueError:
            raise tornado.web.HTTPError(400, reason='Invalid JSON in request body')

    def get_username(self):
        """Returns login username.

        Empty string by default.

        :return: username
        :rtype: str
        """
        return ''

    # ------------------------------------------------------------------ #
    # Blocking / non-blocking boundary                                     #
    # ------------------------------------------------------------------ #

    def is_sync(self):
        """Whether blocking work should run inline on the IOLoop thread.

        Datastore access normally runs on a thread pool so the IOLoop is never
        blocked. When a request carries a ``sync`` query argument the work runs
        inline instead, which makes behaviour deterministic -- this is what the
        unit tests rely on, since an in-memory SQLite datastore cannot be shared
        across threads.

        :rtype: bool
        """
        return self.get_argument('sync', None) is not None

    @tornado.concurrent.run_on_executor
    def _run_on_executor(self, blocking_fn, *args, **kwargs):
        """Runs ``blocking_fn`` on the shared thread pool."""
        return blocking_fn(*args, **kwargs)

    @tornado.gen.engine
    def respond_async(self, blocking_fn, *args, **kwargs):
        """Runs a blocking callable and finishes the request with its result.

        This is the single place where the blocking/non-blocking boundary
        lives. ``blocking_fn`` is expected to return the response body (a
        ``dict``) and may either call :meth:`set_status` to override the status
        code or raise ``tornado.web.HTTPError`` to signal an error.

        Any unexpected exception is caught here and turned into an HTTP 500
        response. That guarantees a failure in background work can never leave
        the request hanging or raise *after* the handler method has already
        returned -- the bug the old fire-and-forget ``*_yield`` wrappers were
        prone to (e.g. deleting a non-existent job).

        :param callable blocking_fn: A blocking callable returning a dict.
        """
        try:
            if self.is_sync():
                result = blocking_fn(*args, **kwargs)
            else:
                result = yield self._run_on_executor(blocking_fn, *args, **kwargs)
        except tornado.web.HTTPError as error:
            self._finish_error(error.status_code, error.reason or 'Bad request')
            return
        except Exception:
            logger.exception('Unhandled error while running %s',
                             getattr(blocking_fn, '__name__', blocking_fn))
            self._finish_error(500, 'Internal server error')
            return

        if not self._finished:
            self.finish(result)

    def _finish_error(self, status_code, message):
        """Finishes the request with a uniform error body, exactly once."""
        if self._finished:
            return
        self.set_status(status_code)
        self.finish({'error': message})

    # ------------------------------------------------------------------ #
    # Response helpers                                                     #
    # ------------------------------------------------------------------ #

    def write_error(self, status_code, **kwargs):
        """Always render errors as JSON instead of an HTML traceback page.

        This keeps the response shape predictable for the front-end: even an
        uncaught ``HTTPError`` (e.g. a validation failure) or a 500 comes back
        as ``{"error": "..."}``.
        """
        message = self._reason or 'Internal server error'
        exc_info = kwargs.get('exc_info')
        if exc_info is not None:
            error = exc_info[1]
            if isinstance(error, tornado.web.HTTPError):
                message = error.reason or message
            else:
                logger.exception('Unhandled exception in handler: %s', self.request.path)
                message = 'Internal server error'
        self.finish({'error': message})

    # ------------------------------------------------------------------ #
    # Shared query-arg helpers                                             #
    # ------------------------------------------------------------------ #

    def get_time_range_args(self, default_minutes=10):
        """Extracts ``time_range_start`` / ``time_range_end`` query args.

        Both default to a window ending now and starting ``default_minutes``
        ago, matching the historical behaviour of the executions and audit-log
        endpoints.

        :param int default_minutes: Size of the default window, in minutes.
        :return: ``(time_range_start, time_range_end)`` ISO-8601 strings.
        :rtype: tuple
        """
        now = datetime.utcnow()
        time_range_end = self.get_argument('time_range_end', now.isoformat())
        earlier = now - timedelta(minutes=default_minutes)
        time_range_start = self.get_argument('time_range_start', earlier.isoformat())
        return time_range_start, time_range_end

    # ------------------------------------------------------------------ #
    # Audit log helper                                                     #
    # ------------------------------------------------------------------ #

    def record_audit_log(self, job_id, job_name, event, description=''):
        """Writes an audit-log entry for the current user (best effort).

        Centralizes the ``user=self.username`` boilerplate so callers only pass
        the event-specific fields. Audit-log writes sit on the critical path of
        every mutating endpoint but are an observability concern, not a
        correctness one: the mutation itself has already happened by the time we
        get here. A failure is therefore logged rather than propagated, so it
        cannot turn a successful mutation into a user-facing error.

        :param str job_id: Job id.
        :param str job_name: Job name.
        :param int event: One of ``constants.AUDIT_LOG_*``.
        :param str description: Optional human readable description. Omitted
            from the write when empty, matching the historical behaviour where
            add/pause/resume events carried no description.
        """
        extra = {'user': self.username}
        if description:
            extra['description'] = description
        try:
            self.datastore.add_audit_log(job_id, job_name, event, **extra)
        except Exception:
            logger.exception('Failed to write audit log: job_id=%s event=%s', job_id, event)
