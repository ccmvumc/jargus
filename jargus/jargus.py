"""main Jargus class.

Interactions with Jargus REDCap should be via the main Jargus class.
Anything outside this class should refer to abstract reports, not redcap
"""
import logging
from datetime import datetime
import os

from redcap import Project, RedcapError

from . import utils_redcap
from .reports import update as update_reports, make_report


logger = logging.getLogger('jargus')


class Jargus:
    """
    Handles reports in redcap.

    Parameters:
        redcap_project (redcap.Project): A REDCap project instance.

    Attributes:
        redcap_project (redcap.Project): The REDCap project instance.
    """

    def __init__(
        self,
        redcap_project: Project=None,
    ):
        """Initialize."""
        self._rc = (redcap_project or self._default_redcap())

    @staticmethod
    def _default_redcap():
        from .utils_redcap import get_jargus_redcap
        return get_jargus_redcap()

    def _dfield(self):
        """Name of redcap filed that stores project name."""
        return self._rc.def_field

    def mains(self, names=None):
        """List of records."""
        rec = self._rc.export_records(forms=['main'])

        if names:
            rec = [x for x in rec if x[self._dfield()] in names]

        rec = [x for x in rec if str(x['main_complete']) == '2']
        return rec

    def reports(self, names=None):
        """List of records."""
        rec = self._rc.export_records(
            forms=['reports'],
            fields=[self._dfield()])

        if names:
            rec = [x for x in rec if x[self._dfield()] in names]

        rec = [x for x in rec if x['redcap_repeat_instrument'] == 'reports']
        rec = [x for x in rec if str(x['reports_complete']) == '2']
        return rec

    def update(self, names=None, choices=None):
        """Update names."""

        if not choices:
            choices = ['reports']

        logger.debug(f'updating:{names}:{choices}')

        if 'reports' in choices:
            # confirm each has report for current month with PDF & zip
            logger.debug('updating progress')
            update_reports(self, names)

    def report(self, name):
        """Create report, report can be any type of file, xlsx, pdf, zip."""
        logger.info(f'writing report:{name}')
        make_report(self, name, os.getcwd())

    def add_report(self, name, report_name, report_date, report_file):
        """Add a record with file, dated and named."""

        # Format for REDCap
        report_datetime = report_date.strftime("%Y-%m-%d %H:%M:%S")

        # Add new record
        try:
            record = {
                self._dfield(): name,
                'redcap_repeat_instrument': 'reports',
                'redcap_repeat_instance': 'new',
                'reports_datetime': report_datetime,
                'reports_name': report_name,
                'reports_complete': '2',
            }
            response = self._rc.import_records([record])
            assert 'count' in response
            logger.debug('created new report record')

            # Determine the new record id
            logger.debug('locating new record')
            _ids = utils_redcap.match_repeat(
                self._rc,
                name,
                'reports',
                'reports_datetime',
                report_datetime)
            repeat_id = _ids[-1]

            # Upload output files
            logger.debug(f'uploading file to:{repeat_id}:{report_file}')
            utils_redcap.upload_file(
                self._rc,
                name,
                'reports_file',
                report_file,
                repeat_id=repeat_id)

        except AssertionError as err:
            logger.error(f'upload failed:{err}')
        except (ValueError, RedcapError) as err:
            logger.error(f'error uploading:{err}')


    def report_setting(self, name, setting):
        """Return the value of the setting."""
        records = self._rc.export_records(records=[name], forms=['main'])
        if not records:
            return None

        rec = records[0]

        return rec.get(f'report_{setting}', rec.get(f'main_{setting}', None))
