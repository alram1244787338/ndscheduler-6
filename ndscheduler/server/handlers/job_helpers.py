"""Job-related helper functions, extracted from jobs.py handler.

This module owns three concerns that previously lived inline in the handler:

1. **build_job_dict**     -- turn an apscheduler Job into the API response dict
2. **generate_modify_description** -- build the HTML diff for audit logs
3. **validate_job_payload** -- validate POST/PUT JSON before calling the scheduler

Keeping these in a separate module means:
  * The handler stays focused on request/response plumbing.
  * Each helper is independently unit-testable (see job_helpers_test.py).
  * Adding a new field to the job response or audit diff only requires
    touching this file, not hunting through the handler.
"""

import tornado.web

from ndscheduler.corescheduler import utils


# ------------------------------------------------------------------ #
# Fields we expose in the API response                                 #
# ------------------------------------------------------------------ #

# These are the cron-related keys returned by utils.get_cron_strings()
CRON_FIELDS = ('month', 'day', 'day_of_week', 'hour', 'minute')

# Fields that are diffed when a job is modified (order = display order)
MODIFY_DIFF_FIELDS = (
    'name',
    'job_class_string',
    'pub_args',
    'minute',
    'hour',
    'day',
    'month',
    'day_of_week',
)

# Fields required in every POST (create job) body
CREATE_REQUIRED_FIELDS = ('name', 'job_class_string')

# At least one of these must be present to form a valid cron schedule
CRON_AT_LEAST_ONE_FIELDS = ('month', 'day', 'hour', 'minute', 'day_of_week')


# ------------------------------------------------------------------ #
# Job dict construction                                                #
# ------------------------------------------------------------------ #

def build_job_dict(job):
    """Transform an apscheduler Job into the API response dictionary.

    :param apscheduler.job.Job job: The job instance.
    :return: Dictionary matching the documented API response schema.
    :rtype: dict
    """
    next_run_time = job.next_run_time.isoformat() if job.next_run_time else ''

    result = {
        'job_id': job.id,
        'name': job.name,
        'next_run_time': next_run_time,
        'job_class_string': utils.get_job_name(job),
        'pub_args': utils.get_job_args(job),
    }
    result.update(utils.get_cron_strings(job))
    return result


# ------------------------------------------------------------------ #
# Modification diff description (for audit logs)                       #
# ------------------------------------------------------------------ #

def _diff_field_html(field_name, old_value, new_value):
    """Return an HTML snippet for one changed field, or '' if unchanged.

    :param str field_name: Name of the field.
    :param old_value: Old value.
    :param new_value: New value.
    :return: HTML string or empty string.
    :rtype: str
    """
    if old_value == new_value:
        return ''
    return (
        '<b>%s</b>: <font color="red">%s</font> => '
        '<font color="green">%s</font><br>'
    ) % (field_name, old_value, new_value)


def generate_modify_description(old_job, new_job):
    """Build an HTML diff string describing what changed between old and new job.

    :param dict old_job: Job dict before modification.
    :param dict new_job: Job dict after modification.
    :return: HTML string (may be empty if nothing changed).
    :rtype: str
    """
    parts = []
    for field in MODIFY_DIFF_FIELDS:
        parts.append(_diff_field_html(field, old_job.get(field), new_job.get(field)))
    return ''.join(parts)


# ------------------------------------------------------------------ #
# Request payload validation                                           #
# ------------------------------------------------------------------ #

def validate_job_payload(json_args):
    """Validate the JSON body for creating a job.

    Raises ``tornado.web.HTTPError(400)`` if validation fails.

    Rules:
      * ``name`` and ``job_class_string`` are always required.
      * At least one cron field (``month``, ``day``, ``hour``, ``minute``,
        ``day_of_week``) must be present.

    :param dict json_args: Parsed JSON body (may be None).
    :raises tornado.web.HTTPError: 400 on invalid input.
    """
    if not json_args or not isinstance(json_args, dict):
        raise tornado.web.HTTPError(400, reason='Request body must be a JSON object')

    for field in CREATE_REQUIRED_FIELDS:
        if field not in json_args:
            raise tornado.web.HTTPError(
                400, reason='Require this parameter: %s' % field)

    has_cron = any(f in json_args for f in CRON_AT_LEAST_ONE_FIELDS)
    if not has_cron:
        raise tornado.web.HTTPError(
            400,
            reason='Require at least one of following parameters: %s'
                   % str(list(CRON_AT_LEAST_ONE_FIELDS)),
        )


def get_job_or_404(scheduler_manager, job_id):
    """Fetch a job, raising HTTPError(400) if it does not exist.

    This centralizes the "job not found" check so handlers do not repeat it.

    :param scheduler_manager: The SchedulerManager instance.
    :param str job_id: Job id.
    :return: The apscheduler Job.
    :raises tornado.web.HTTPError: 400 if the job is not found.
    """
    job = scheduler_manager.get_job(job_id)
    if not job:
        raise tornado.web.HTTPError(400, reason='Job not found: %s' % job_id)
    return job
