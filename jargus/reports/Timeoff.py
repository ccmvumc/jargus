import os
from datetime import datetime, timedelta
import logging

import pandas as pd

from ..utils_redcap import get_redcap
from ..utils_email import send_email


logger = logging.getLogger('jargus.reports.timeoff')


NAME2EMAIL = {
    'Dr. Newhouse': 'paul.newhouse@vumc.org',
    'Amy Boegel': 'amy.r.boegel@vumc.org',
    'Sydni Hill': 'sydni.hill@vumc.org'}


# These are the same across the whole redcap
EVENTID = '156529'
PROJECTID = '66924'
PAGENAME = 'ccm_time_off'

# Formatting for the html table
TABLE = '<table cellspacing="0" cellpadding="4" rules="rows" style="color:#1f2240;background-color:#ffffff">'

# Formatting for the html table header
TH = '<th style="text-align:center;border-bottom:thin;padding:10">'

# Formatting for the html data cell
TD = '<td style="text-align:center;">'

HTML_TEMPLATE = '''<!DOCTYPE html>
<html><body>
    <h3>{0}: {1} Items Pending</h3>
    <table>
        <tr>
            <th>Record</th>
            <th>Name</th>
            <th>Start Date</th>
            <th>End Date</th>
        </tr>
        {2}
    </table><hr>
</body</html>'''

ROW_TEMPLATE = '''<tr>
    <td><a href="https://redcap.vumc.org/redcap_v15.1.1/DataEntry/index.php?pid={projectid}&page={pagename}&id={recordid}&event_id={eventid}&instance={instanceid}" target="_blank">&nbsp;&nbsp;{recordid} ({instanceid})&nbsp;&nbsp;</a></td>
    <td>{name}</td>
    <td>{startdate}</td>
    <td>{enddate}</td>
</tr>'''

RECENT_TEMPLATE = '''<!DOCTYPE html>
<html><body>
    <table>
        <tr>
            <th>Name</th>
            <th>Start Date</th>
            <th>End Date</th>
            <th>Status</th>
        </tr>
        <tr>
            <td>{name}</td>
            <td>{startdate}</td>
            <td>{enddate}</td>
            <td>{approval}</td>
        </tr>
    </table><hr>
</body</html>'''


def get_pending(df):
    if df.empty:
        return df

    # Filter to only include records that are ready and pending
    dfp = df[df['notify_dr_newhouse'] == 'Ready to notify Dr. Newhouse']
    dfp = dfp[(dfp['approval'].isnull()) | (dfp['approval'] == '')]

    return dfp


def get_completed(df):
    if df.empty:
        return df

    # Filter to only include records that are ready and complete
    dfc = df[df['notify_dr_newhouse'] == 'Ready to notify Dr. Newhouse']
    dfc = dfc[dfc['approval'] != '']

    return dfc


def get_recent(df, previous):
    # This is different from the other reports b/c we need to know the value
    # of approval. So, instead of determining which items that were on
    # yesterday's
    # report that are not on today's report, we are doing the opposite
    # to determine which items which have an approval value were not in that
    # list yesterday.

    # read previous day file and compare to only include recently changed
    dfp = load_previous_pending(previous)

    if dfp is None or dfp.empty:
        return dfp

    dfc = get_completed(df)

    # Ensure consistent types
    dfp['record_id'] = dfp['record_id'].astype('int')
    dfp['redcap_repeat_instance'] = dfp['redcap_repeat_instance'].astype('int')
    dfc['record_id'] = dfc['record_id'].astype('int')
    dfc['redcap_repeat_instance'] = dfc['redcap_repeat_instance'].astype('int')

    # Set index of each dataframe based on uniqueness across two columns
    dfp = dfp.set_index(['record_id', 'redcap_repeat_instance'])
    dfc = dfc.set_index(['record_id', 'redcap_repeat_instance'])

    # Filter to include those records that are in the completed list today AND
    # were in the the pending list yesterday
    dfc = dfc[dfc.index.isin(dfp.index)]

    if dfc is None or dfc.empty:
        return dfc

    return dfc


def load_previous_pending(filename):
    if not os.path.exists(filename):
        return None

    # Load df from file, explicitly use record_id as index
    logger.debug(f'loading previous file:{filename}')
    df = pd.read_excel(
        filename,
        dtype={'notify_dr_newhouse': 'string', 'approval': 'string'})

    if df is None or df.empty:
        return df

    # Filter to only include pending
    df = df[(df.notify_dr_newhouse == 'Ready to notify Dr. Newhouse')]
    df = df[((df.approval.isnull() | (df.approval == '')))]

    return df


def get_approver_content(df, approver):
    list_content = ''
    list_count = len(df)
    for index, row in df.iterrows():
        row_content = ROW_TEMPLATE.format(
            projectid=PROJECTID,
            pagename=PAGENAME,
            name=row['name'],
            recordid=row['record_id'],
            eventid=EVENTID,
            startdate=row['time_off_start_date'],
            enddate=row['time_off_end_date'],
            instanceid=row['redcap_repeat_instance'])

        list_content += row_content

    content = HTML_TEMPLATE.format(approver, list_count, list_content)
    content = content.replace('<table>', TABLE)
    content = content.replace('<td>', TD)
    content = content.replace('<th>', TH)

    return content


def get_recent_content(row):
    _name = row['name']
    _startdate = row['time_off_start_date']
    _enddate = row['time_off_end_date']
    _approval = row['approval']

    content = RECENT_TEMPLATE.format(
        name=_name,
        startdate=_startdate,
        enddate=_enddate,
        approval=_approval)

    # Inject some formatting
    content = content.replace('<table>', TABLE)
    content = content.replace('<td>', TD)
    content = content.replace('<th>', TH)

    return content


def save_data(df, outdir):
    name = 'timeoff'
    now = datetime.now().strftime("%Y-%m-%d")
    filename = os.path.join(outdir, f'{name}_report_{now}.xlsx')
    if os.path.exists(filename):
        now = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = os.path.join(outdir, f'{name}_report_{now}.xlsx')

    df.to_excel(filename, index=False)

    return filename


def make_report(outdir, previous):
    today = datetime.now().strftime("%Y-%m-%d")

    # Load the redcap db
    proj = get_redcap(PROJECTID)
    df = pd.DataFrame(proj.export_records(raw_or_label='label'))

    # Dr. Newhouse
    dfn = get_pending(df)
    _name = 'Dr. Newhouse'
    _email = NAME2EMAIL[_name]
    _content = get_approver_content(dfn, _name)

    if (len(dfn) == 0):
        _subject = f'No PTO Requests {today}'
    else:
        _subject = f'PTO Requests {today}'

    send_email(_content, _email, _subject)

    # COORDINATORS recently completed and email for each item
    if previous:
        dfc = get_recent(df, previous)

        if not dfc.empty:
            for i, row in dfc.iterrows():
                _email = NAME2EMAIL[row['name']]
                _content = get_recent_content(row)
                _subject = f'PTO Requests {today}'
                send_email(_content, _email, _subject)
        else:
            logger.debug('no recently completed, not sending any more emails')

    # Return saved data
    return save_data(df, outdir)
