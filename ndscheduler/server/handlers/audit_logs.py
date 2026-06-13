"""Handler for audit logs endpoint.

  * GET /api/v1/logs  -- return audit logs within a time window
"""

import tornado.web

from ndscheduler.server.handlers import base


class Handler(base.BaseHandler):
    """Handles ``GET /api/v1/logs``."""

    def _get_logs(self):
        """Returns the audit logs within the requested time window.

        :rtype: dict
        """
        time_range_start, time_range_end = self.get_time_range_args()
        return self.datastore.get_audit_logs(time_range_start, time_range_end)

    @tornado.web.removeslash
    @tornado.web.asynchronous
    def get(self):
        """GET ``/api/v1/logs``.

        ``time_range_start`` / ``time_range_end`` query arguments bound the
        window (defaulting to the last 10 minutes).
        """
        self.respond_async(self._get_logs)
