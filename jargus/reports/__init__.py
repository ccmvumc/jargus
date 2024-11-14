"""Jargus reports."""
import os
import tempfile
from datetime import datetime
import logging

from ..utils_redcap import download_named_file

# Load reports
from . import ImageRead
from . import Progress
from . import Signoff
from . import Timeoff
from . import Tracking
from . import registry
from . import registryb


logger = logging.getLogger('jargus.reports')


def update(jargus, names=None):
    """Update reports."""

    mains = jargus.mains()
    dfield = jargus._dfield()

    if names:
        mains = [m for m in mains if m[dfield] in names]

    for m in mains:
        name = m[dfield]
        freq = m['report_freq'].lower()
        emailto = m['report_emailto']
        emailto = list(x.strip() for x in emailto.split('\n'))
        logger.debug(f'updating report:{name}')
        _update_report(jargus, name, freq, emailto)


def _update_report(jargus, name, freq, emailto):
    logger.debug(f'making report:{name}')

    reps = jargus.reports(names=[name])

    # check that each has report for current month with PDF and zip
    report_date = datetime.now()

    # Only update reports on weekdays after 6am
    if report_date.weekday() > 4 or report_date.hour < 6:
        return

    if freq == 'daily':
        report_name = report_date.strftime("%Y-%m-%d")
    elif freq == 'monthly':
        report_name = report_date.strftime("%B%Y")
    else:
        report_name = report_date.strftime("%Y")

    has_cur = any(d.get('reports_name') == report_name for d in reps)
    if has_cur:
        logger.debug(f'record exists:{name}:{report_name}')
        return

    logger.debug(f'making new record:{name}')

    with tempfile.TemporaryDirectory() as outdir:
        if len(reps) > 0:
            # Load the previous report
            previous = reps[-1]
            previous_file = download_named_file(
                jargus._rc,
                name,
                'reports_file',
                outdir,
                repeat_id=previous['redcap_repeat_instance'])
        else:
            previous_file = None

        report_file = make_report(
            jargus,
            name,
            outdir,
            emailto=emailto,
            previous=previous_file)

        if not report_file:
            logger.error(f'failed to create report:{report_file}')
            return

        jargus.add_report(name, report_name, report_date, report_file)


def make_report(jargus, name, outdir, emailto=None, previous=None):
    """Make report of name type."""

    if name == 'ImageRead':
        return ImageRead.make_report(outdir, emailto, previous)
    elif name == 'Signoff':
        return Signoff.make_report(outdir, emailto, previous)
    elif name == 'Progress':
        return Progress.make_report(outdir, emailto)
    elif name == 'Timeoff':
        return Timeoff.make_report(outdir, previous)
    elif name == 'Tracking':
        return Tracking.make_report(outdir, emailto)
    elif name == 'Registry':
        return registryb.make_report(outdir, emailto)
    else:
        logger.error(f'unknown report name:{name}')
        return None
