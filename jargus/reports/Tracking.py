import logging
from datetime import datetime
import os

import pandas as pd

from ..utils_redcap import get_redcap
from ..utils_email import send_email


logger = logging.getLogger('jargus.reports.tracking')


# Formatting for the html table
TABLE = '<table cellspacing="0" cellpadding="4" rules="rows" style="color:#1f2240;background-color:#ffffff">'

# Formatting for the html table header
TH = '<th style="text-align:left;border-bottom:thin;padding:10">'

# Formatting for the html data cell
TD = '<td style="text-align:left;">'

HTML_TEMPLATE = '''<!DOCTYPE html>
<html><body>
    <h3>{0}: {1} Total Items Pending</h3>
    <hr>
    {2}
</body></html>'''

STATUS_TEMPLATE = '''
    <h3>{0}: {1}</h3>
    <table>
        <tr>
            <th>Tracking ID</th>
            <th>Study</th>
            <th>Status</th>
            <th>Prescreeners ID</th>
        </tr>
        {2}
    </table><hr>'''

ROW_TEMPLATE = '''<tr>
    <td><a href="https://redcap.vanderbilt.edu/redcap_v13.2.3/DataEntry/record_home.php?pid=155254&arm=1&id={tid}" target="_blank">&nbsp;&nbsp;[{tid}] {initials}&nbsp;&nbsp;</a></td>
    <td>{study}</td>
    <td>{status}</td>
    <td><a href="https://redcap.vanderbilt.edu/redcap_v13.2.3/DataEntry/record_home.php?pid=151393&arm=2&id={pid}" target="_blank">&nbsp;&nbsp;[{pid}]&nbsp;&nbsp;{pdate}</a></td>
</tr>'''


ROW_TEMPLATE_URG = '''<tr>
    <td style="background-color: #FFFF00;"><a href="https://redcap.vanderbilt.edu/redcap_v13.2.3/DataEntry/record_home.php?pid=155254&arm=1&id={tid}" target="_blank">&nbsp;&nbsp;[{tid}] {initials}&nbsp;&nbsp;</a></td>
    <td style="background-color: #FFFF00;">{study}</td>
    <td style="background-color: #FFFF00;">{status} </td>
    <td style="background-color: #FFFF00;"><a href="https://redcap.vanderbilt.edu/redcap_v13.2.3/DataEntry/record_home.php?pid=151393&arm=2&id={pid}" target="_blank">&nbsp;&nbsp;[{pid}]&nbsp;&nbsp;{pdate}</a></td>
</tr>'''


def get_prescreeners_id2date(rc):
    id2date = {}
    date_fields = [x for x in rc.field_names if x.startswith('prescreener_date') or x.startswith('date3_v2')]

    records = rc.export_records(fields=['record_id'] + date_fields)
    for r in records:
        record_id = r['record_id']

        # Find the pdate
        pdate = None
        for date_field in date_fields:
            if date_field not in r:
                continue

            d = r[date_field]

            if d:
                if not pdate:
                    # Store the new name
                    pdate = d
                elif d == pdate:
                    # Already set
                    pass
                else:
                    # Mismatch
                    continue

        if not pdate:
            pass
        elif record_id not in id2date:
            id2date[record_id] = pdate
        elif id2date[record_id] == pdate:
            pass
        else:
            logger.debug(f'duplicated name using latest record:{record_id}')
            id2date[record_id] = pdate

    return id2date


def get_prescreeners_name2id(rc):
    name2id = {}
    name_fields = [x for x in rc.field_names if (x.startswith('name_v2') or x.startswith('name9'))]

    records = rc.export_records(fields=['record_id'] + name_fields)
    for r in records:
        record_id = r['record_id']

        # Find the name while checking for mismatches across fields=
        name = None
        for name_field in name_fields:
            if name_field not in r:
                continue

            n = r[name_field]

            # Remove any leading/trailing whitespace
            n = n.strip()

            if n:
                if not name:
                    # Store the new name
                    name = n
                elif n == name:
                    # Already set
                    pass
                else:
                    # Mismatch
                    continue

        # If already found, check that same record_id found for name
        if not name:
            pass
        elif name not in name2id:
            name2id[name] = record_id
        elif name2id[name] == record_id:
            pass
        else:
            logger.debug(f'duplicated name using latest record:{record_id}')
            name2id[name] = record_id

    return name2id


def get_tracking_id2name(rc):
    id2name = {}
    name_fields = ['name', 'name2', 'name3', 'participant_name']
    records = rc.export_records(fields=['record_id'] + name_fields)

    for r in records:
        record_id = r['record_id']

        # Find the name while checking for mismatches across fields=
        name = None
        for name_field in name_fields:
            if name_field not in r:
                continue

            n = r[name_field]
            n = n.strip()

            if n:
                if not name:
                    # Store the new name
                    name = n
                elif n == name:
                    # Already set
                    pass
                else:
                    # Mismatch
                    continue

        # If already found, check that same record_id found for name
        if not name:
            pass
        elif record_id not in id2name:
            id2name[record_id] = name
        elif id2name[record_id] == name:
            pass
        else:
            logger.debug(f'duplicated ID, using latest record:{record_id}:"{name}"')
            id2name[record_id] = name

    return id2name


def get_initials(name):
    return name[0] + name.split()[1][0]


def load_tracking_open(rct, rcp):
    data = []

    records = rct.export_records(
        export_checkbox_labels=True,
        export_blank_for_gray_form_status=True,
        raw_or_label='label',
    )

    # Filter to only Unverified, this also excludes blanks
    unverified = [x for x in records if x['study_eligibility_information_complete'] == 'Unverified']
    saved = [x for x in records if x['study_eligibility_information_complete']]

    all_ids = list(set([x['record_id'] for x in records]))
    saved_ids = list(set([x['record_id'] for x in saved]))
    unverified_ids = list(set([x['record_id'] for x in unverified]))
    unsaved_ids = list(set(all_ids) - set(saved_ids))
    record_ids = unverified_ids + unsaved_ids

    # Get record ids as sorted ints then convert back to strings
    record_ids = sorted(list(set([int(x) for x in record_ids])))
    record_ids = [str(x) for x in record_ids]

    # process each record id
    for r in record_ids:
        # Reset
        new_record = {
            'ID': r,
            'STUDY': '',
            'PRESCREEN': '',
            'URG': '',
            'STATUS': 'UNKNOWN',
            'NOTES': '',
            'COMPLETE': '',
            'PRESCREENERSID': '',
        }

        # Get data for this record id
        cur_records = [x for x in records if x['record_id'] == r]

        # Load the data from all records including from repeating instruments
        for cur_data in cur_records:
            for k, v in cur_data.items():
                if not v or v == '':
                    # no value found
                    continue
                elif k == 'which_study':
                    new_record['STUDY'] = v
                elif k == 'are_they_eligbile_for_that':
                    new_record['PRESCREEN'] = v
                elif k == 'urp_definition':
                    new_record['URG'] = v
                elif k == 'enrollment_status1':
                    new_record['STATUS'] = v
                elif k == 'coordinator_notes':
                    new_record['NOTES'] = v

        # Append record
        data.append(new_record)

    # Use tid to get name, then name to get pid
    rcp_name2id = get_prescreeners_name2id(rcp)
    rct_id2name = get_tracking_id2name(rct)
    rcp_id2date = get_prescreeners_id2date(rcp)

    for d in data:
        tid = d['ID']

        # Get record in prescreeners
        name = rct_id2name.get(tid, None)

        if not name:
            continue

        d['INITIALS'] = get_initials(name)

        pid = rcp_name2id.get(name, 'NotFound')
        pdate = rcp_id2date.get(pid, '')
        if pdate:
            delta = datetime.now() - datetime.strptime(pdate, '%Y-%m-%d')
            if delta.days > 75:
                pdate = f'<span style="color:red">{pdate}</span>'

        d['PRESCREENERSID'] = pid
        d['PRESCREENERSDATE'] = pdate

    if len(data) > 0:
        df = pd.DataFrame(data)
    else:
        df = pd.DataFrame(
            columns=['ID', 'STUDY', 'PRESCREENERSID', 'PRESCREENERSDATE'])

    df = df.set_index('ID')
    return df


def get_content(df):
    content = ''

    status_list = df['STATUS'].unique()

    for status in sorted(status_list):
        status_df = df[df.STATUS == status]
        status_content = get_status_content(status_df)
        status_content = STATUS_TEMPLATE.format(len(status_df), status, status_content)
        content += status_content

    content = HTML_TEMPLATE.format('CCM Tracking', len(df), content)

    # Interject formatting
    content = content.replace('<table>', TABLE)
    content = content.replace('<td>', TD)
    content = content.replace('<th>', TH)
    content += '<p>This report includes all records where Study Eligibility is Unverified.'

    return content


def get_status_content(df):
    content = ''
    for index, row in df.iterrows():
        if row.get('URG', '') == 'Yes':
            row_content = ROW_TEMPLATE_URG.format(
                tid=index,
                pid=row['PRESCREENERSID'],
                study=row['STUDY'],
                status=row['STATUS'],
                pdate=row['PRESCREENERSDATE'],
                initials=row['INITIALS'],
            )
        else:
            row_content = ROW_TEMPLATE.format(
                tid=index,
                pid=row['PRESCREENERSID'],
                study=row['STUDY'],
                status=row['STATUS'],
                pdate=row['PRESCREENERSDATE'],
                initials=row['INITIALS'],
            )

        content += row_content

    return content


def save_data(df, outdir):
    name = 'tracking'
    now = datetime.now().strftime("%Y-%m-%d")
    filename = os.path.join(outdir, f'{name}_report_{now}.xlsx')
    if os.path.exists(filename):
        now = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = os.path.join(outdir, f'{name}_report_{now}.xlsx')

    df.to_excel(filename)

    return filename


def make_report(outdir, emailto):
    today = datetime.now().strftime("%Y-%m-%d")

    subject = f'CCM Tracking {today}'

    # Get Tracking redcap
    rct = get_redcap('155254')

    # Get Prescreeners redcap
    rcp = get_redcap('151393')

    # Load open records from Tracking with link to prescreener
    df = load_tracking_open(rct, rcp)

    # Get email content
    content = get_content(df)

    # Email report content
    send_email(content, emailto, subject)

    # Return the report data for saving
    return save_data(df, outdir)
