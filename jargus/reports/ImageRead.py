import os
from datetime import datetime, timedelta
import logging

import pandas as pd

from ..utils_redcap import get_redcap
from ..utils_email import send_email


logger = logging.getLogger('jargus.reports.ImageRead')


CLIN_NAME = 'Dr. Martin'
CLIN_EMAIL = 'dann.martin@vumc.org'
PROJECTID = '143314'

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
            <th>Study</th>
            <th>ID</th>
            <th>Coordinator</th>
            <th>Type</th>
            <th>Due</th>
        </tr>
        {2}
    </table><hr>
</body</html>'''

ROW_TEMPLATE = '''<tr>
    <td><a href="https://redcap.vanderbilt.edu/redcap_v12.0.3/DataEntry/index.php?pid=143314&id={recordid}&page=mri_reviews" target="_blank">&nbsp;&nbsp;{recordid}&nbsp;&nbsp;</a></td>
    <td>{study}</td>
    <td>{subjectid}</td>
    <td>{coordinator}</td>
    <td>{filetype}</td>
    <td>{duedate}</td>
</tr>'''

DONE_TEMPLATE = '''<!DOCTYPE html>
<html><body>
    <h3> {0} Recently Completed Items</h3>
    <table>
        <tr>
            <th>Record</th>
            <th>Study</th>
            <th>ID</th>
            <th>Coordinator</th>
            <th>Type</th>
            <th>Due</th>
        </tr>
        {1}
    </table><hr>
</body</html>'''

DONEROW_TEMPLATE = '''<tr>
    <td><a href="https://redcap.vanderbilt.edu/redcap_v12.0.3/DataEntry/index.php?pid=143314&id={recordid}&page=mri_reviews" target="_blank">&nbsp;&nbsp;{recordid}&nbsp;&nbsp;</a></td>
    <td>{study}</td>
    <td>{subjectid}</td>
    <td>{coordinator}</td>
    <td>{filetype}</td>
    <td>{duedate}</td>
</tr>'''


LINK_TEMPLATE = '<a href="{0}" target="_blank">SCAN</a>'


def get_pending(df):
    columns = ['c_name', 'study', 'id', 'links', 'date_mri_report_needed_by']

    if df.empty:
        return df

    # Filter to only include records that are ready for clinician but
    # not ready for coordinator
    dfn = df[
        (df.ready_to_review == 'Yes') &
        (df.ready_for_coordinator.isnull())
    ]

    return dfn[columns]


def get_completed(df, previous):
    # Read previous day file and compare to only include recently changed
    columns = ['c_name', 'study', 'id', 'links', 'date_mri_report_needed_by']

    dfc = load_previous_pending(previous)

    if dfc is None or dfc.empty:
        return dfc

    dfp = df[
        (df.ready_to_review == 'Yes') &
        (df.ready_for_coordinator.isnull())
    ]

    # Filter to records that were pending yesterday but not today
    dfc = dfc[~(dfc.index.isin(dfp.index))]

    if dfc is None or dfc.empty:
        return dfc

    return dfc[columns]


def get_completed_content(df):
    list_content = ''
    list_count = 0

    if df is not None:
        list_count = len(df)
        for index, row in df.iterrows():
            if pd.notnull(row['links']):
                filetype = LINK_TEMPLATE.format(row['links'])

            row_content = DONEROW_TEMPLATE.format(
                recordid=index,
                study=row['study'],
                subjectid=row['id'],
                filetype=filetype,
                coordinator=row['c_name'],
                duedate=row['date_mri_report_needed_by'])

            list_content += row_content

    content = DONE_TEMPLATE.format(list_count, list_content)
    content = content.replace('<table>', TABLE)
    content = content.replace('<td>', TD)
    content = content.replace('<th>', TH)

    return content


def get_coord_content(dflist, clin_list, dfc):
    content = ''
    content += get_completed_content(dfc)

    for i, df in enumerate(dflist):
        content += get_clin_content(df, clin_list[i])

    return content


def get_clin_content(df, clin):
    list_content = ''
    list_count = len(df)
    for index, row in df.iterrows():
        if pd.notnull(row['links']):
            filetype = LINK_TEMPLATE.format(row['links'])

        row_content = ROW_TEMPLATE.format(
            recordid=index,
            study=row['study'],
            subjectid=row['id'],
            filetype=filetype,
            coordinator=row['c_name'],
            duedate=row['date_mri_report_needed_by'])

        list_content += row_content

    content = HTML_TEMPLATE.format(clin, list_count, list_content)
    content = content.replace('<table>', TABLE)
    content = content.replace('<td>', TD)
    content = content.replace('<th>', TH)

    return content


def save_data(df, outdir):
    name = 'ImageRead'
    now = datetime.now().strftime("%Y-%m-%d")
    filename = os.path.join(outdir, f'{name}_report_{now}.xlsx')
    if os.path.exists(filename):
        now = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = os.path.join(outdir, f'{name}_report_{now}.xlsx')

    df.to_excel(filename)

    return filename


def load_previous_pending(filename):
    if not os.path.exists(filename):
        return None

    # Load df from file, explicitly use record_id as index
    df = pd.read_excel(filename, index_col='record_id')
    if not df.empty:
        df = df[
            (df.ready_to_review == 'Yes') &
            (df.ready_for_coordinator.isnull())
        ]

    return df


def make_report(outdir, emailto, previous=None):
    email_subject = 'CCM Pending Image Read Report'

    # Load the redcap db
    proj = get_redcap(PROJECTID)
    df = proj.export_records(format_type='df', raw_or_label='label')

    # Email clinician
    df1 = get_pending(df)
    _content = get_clin_content(df1, CLIN_NAME)
    send_email(_content, CLIN_EMAIL, email_subject)

    if previous:
        dfc = get_completed(df, previous)
    else:
        dfc = None

    # Send coord email
    _content = get_coord_content([df1], CLIN_NAME, dfc)
    send_email(_content, emailto, email_subject)

    # Return saved file
    return save_data(df, outdir)
