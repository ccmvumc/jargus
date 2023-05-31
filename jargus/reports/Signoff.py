import os
from datetime import datetime, timedelta

import redcap
import pandas as pd

from ..utils_redcap import get_redcap
from ..utils_email import send_email

PROJECTID = '131071'

TABLE = '<table cellspacing="0" cellpadding="4" rules="rows" style="color:#1f2240;background-color:#ffffff">'

TH = '<th style="text-align:center;border-bottom:thin;padding:10">'

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
        </tr>
        {2}
    </table><hr>
</body</html>'''

ROW_TEMPLATE = '''<tr>
    <td><a href="https://redcap.vanderbilt.edu/redcap_v11.0.0/DataEntry/index.php?pid=131071&id={recordid}&page=clinician_signature" target="_blank">&nbsp;&nbsp;{recordid}&nbsp;&nbsp;</a></td>
    <td>{study}</td>
    <td>{subjectid}</td>
    <td>{coordinator}</td>
    <td>{filetype}</td>
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
        </tr>
        {1}
    </table><hr>
</body</html>'''

DONEROW_TEMPLATE = '''<tr>
    <td><a href="https://redcap.vanderbilt.edu/redcap_v11.0.0/DataEntry/index.php?pid=131071&id={recordid}&page=clinician_signature" target="_blank">&nbsp;&nbsp;{recordid}&nbsp;&nbsp;</a></td>
    <td>{study}</td>
    <td>{subjectid}</td>
    <td>{coordinator}</td>
    <td>{filetype}</td>
</tr>'''


LINK_TEMPLATE = '<a href="{0}" target="_blank">{1}</a>'


def get_pending(df, clin):
    columns = [
        'date', 'c_name', 'study', 'id', 'file_type', 'file_tbs', 'links']

    if df.empty:
        return df

    # Filter to only include records that are ready for clinician and
    # not ready for coordinator
    dfn = df[
        (df.ready_to_review == 'Yes') &
        (df[clin] == 'Checked') &
        (df.ready_for_coordinator.isnull()) &
        (df.ready_for_coordinator_2.isnull())]

    return dfn[columns]


def get_completed(df, previous):
    # read previous day file and compare to only include recently changed
    columns = [
        'date', 'c_name', 'study', 'id', 'file_type', 'file_tbs', 'links']

    dfc = load_previous_pending(previous)

    if dfc is None or dfc.empty:
        return dfc

    dfp = df[
        (df.ready_to_review == 'Yes') &
        (df.ready_for_coordinator.isnull()) &
        (df.ready_for_coordinator_2.isnull())]

    # Filter to records that were pending yesterday but not today
    dfc = dfc[~(dfc.index.isin(dfp.index))]

    if dfc is None or dfc.empty:
        return dfc

    return dfc[columns]


def load_previous_pending(filename):
    if not os.path.exists(filename):
        return None

    # Load df from file, explicitly use record_id as index
    df = pd.read_excel(filename, index_col='record_id')
    if not df.empty:
        df = df[
            (df.ready_to_review == 'Yes') &
            (df.ready_for_coordinator.isnull()) &
            (df.ready_for_coordinator_2.isnull())]

    return df


def get_completed_content(df):
    list_content = ''
    list_count = 0

    if df is not None:
        list_count = len(df)
        for index, row in df.iterrows():
            filetype = row['file_type']
            if pd.notnull(row['links']):
                filetype = LINK_TEMPLATE.format(row['links'], filetype)

            row_content = DONEROW_TEMPLATE.format(
                recordid=index,
                study=row['study'],
                subjectid=row['id'],
                filetype=filetype,
                coordinator=row['c_name'])

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
        content += get_html_content(df, clin_list[i])

    return content


def get_html_content(df, clin):
    list_content = ''
    list_count = len(df)
    for index, row in df.iterrows():
        filetype = row['file_type']
        if pd.notnull(row['links']):
            filetype = LINK_TEMPLATE.format(row['links'], filetype)

        row_content = ROW_TEMPLATE.format(
            recordid=index,
            study=row['study'],
            subjectid=row['id'],
            filetype=filetype,
            coordinator=row['c_name'])

        list_content += row_content

    content = HTML_TEMPLATE.format(clin, list_count, list_content)
    content = content.replace('<table>', TABLE)
    content = content.replace('<td>', TD)
    content = content.replace('<th>', TH)

    return content


def save_data(df, outdir):
    name = 'signature'
    now = datetime.now().strftime("%Y-%m-%d")
    filename = os.path.join(outdir, f'{name}_report_{now}.xlsx')
    if os.path.exists(filename):
        now = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = os.path.join(outdir, f'{name}_report_{now}.xlsx')

    df.to_excel(filename)

    return filename


def make_report(outdir, emailto, previous=None):
    email_subject = 'CCM Pending Signature Report'

    # Load the doc signing db
    proj = get_redcap(PROJECTID)
    df = proj.export_records(format_type='df', raw_or_label='label')

    # Save to file
    report_file = save_data(df, outdir)

    # Nancy
    df1 = get_pending(df, 'corresponding_clinician___1')
    _name = 'Nancy Morton'
    _content = get_html_content(df1, _name)
    _email = 'nancy.morton@vumc.org'
    send_email(_content, _email, email_subject)

    # Newhouse
    df2 = get_pending(df, 'corresponding_clinician___2')
    _name = 'Paul Newhouse'
    _content = get_html_content(df2, _name)
    _email = 'paul.newhouse@vumc.org'
    send_email(_content, _email, email_subject)

    # Andrews
    df3 = get_pending(df, 'corresponding_clinician___3')
    _name = 'Patricia Andrews'
    _content = get_html_content(df3, _name)
    _email = 'patricia.andrews@vumc.org'
    send_email(_content, _email, email_subject)

    # Get recently completed
    if previous:
        dfc = get_completed(df, previous)
    else:
        dfc = None

    # Send coord email
    _content = get_coord_content([df1, df2, df3], CLINICIANS, dfc)
    send_email(_content, emailto, email_subject)

    return report_file
