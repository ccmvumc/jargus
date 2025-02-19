import logging
from datetime import datetime
import os

import pandas as pd

from ...utils_redcap import get_redcap
from ...utils_email import send_email


logger = logging.getLogger('jargus.reports.registry')

# Redcap project ID
PID = '183871'

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
            <th>Registry ID</th>
            <th>Study</th>
            <th>Status</th>
        </tr>
        {2}
    </table><hr>'''

ROW_TEMPLATE = '''<tr>
    <td><a href="https://redcap.vumc.org/redcap_v15.1.1/DataEntry/record_home.php?pid={pid}&arm=1&id={tid}" target="_blank">&nbsp;&nbsp;[{tid}] {initials}&nbsp;&nbsp;</a></td>
    <td>{study}</td>
    <td>{status}</td>
</tr>'''


ROW_TEMPLATE_URG = '''<tr>
    <td style="background-color: #FFFF00;"><a href="https://redcap.vumc.org/redcap_v15.1.1/DataEntry/record_home.php?pid={pid}&arm=1&id={tid}" target="_blank">&nbsp;&nbsp;[{tid}] {initials}&nbsp;&nbsp;</a></td>
    <td style="background-color: #FFFF00;">{study}</td>
    <td style="background-color: #FFFF00;">{status} </td>
</tr>'''

PRESCREENER_TEMPLATE = '''<td><a href="https://redcap.vumc.org/redcap_v15.1.1/DataEntry/index.php?pid={pid}&id={tid}&page={ppage}&event_id={eid}&instance={rid}" target="_blank"> Prescreener: {ptype} {pdate}</a></td>'''


def get_initials(first_name, last_name):
    try:
        return first_name.upper()[0] + last_name.upper()[0]
    except IndexError as err:
        logger.debug(f'cannot find intials:{err}')
        return ''


def load_all(rc):
    data = []

    records = rc.export_records(
        export_checkbox_labels=True,
        export_blank_for_gray_form_status=True,
        raw_or_label='label',
    )

    registry = [x for x in records if x['redcap_event_name'] == 'CCM Registry']

    # process each record id
    for r in registry:
        # Reset
        d = {
            'ID': r['record_id'],
            'STUDY': '',
            'URG': '',
            'STATUS': 'TBD',
            'NOTES': '',
            'COMPLETE': '',
            'INITIALS': '',
            'SOURCE': '',
            'SOURCE2': '',
            'MDATE': '',
            'MTYPE': '',
            'MSCORE': '',
            'MRESULT': '',
        }

        # Get them memory screening
        if r['memory_assessment_score_v2']:
            d['MSCORE'] = r['memory_assessment_score_v2']
            d['MDATE'] = r['when_is_the_memory_screeni_v2']

            if r['what_memory_assessment_did_v2___1']:
                d['MTYPE'] = r['what_memory_assessment_did_v2___1']
            elif r['what_memory_assessment_did_v2___2']:
                d['MTYPE'] = r['what_memory_assessment_did_v2___2']
            elif r['what_memory_assessment_did_v2___3']:
                d['MTYPE'] = r['what_memory_assessment_did_v2___3']

            d['MRESULT'] = r['impaired_v2']

        # Get the source information
        if r['referral_source']:
            d['SOURCE'] = r['referral_source']
            if r['physician_referals']:
                d['SOURCE2'] = r['physician_referals']

        d['STUDY'] = r['study_name3']

        # Find the latest status
        if r['status_of_the_screening_vi_3']:
            d['STATUS'] = r['status_of_the_screening_vi_3']
        elif r['recruitment_status']:
            d['STATUS'] = r['recruitment_status']

        d['URG'] = r['urp_definition']

        first_name = r['name3_v2']
        last_name = r['last_name_2']

        if first_name and last_name:
            d['INITIALS'] = get_initials(first_name, last_name)

        for p in records:
            # Find the prescreeners, select the latest, link it
            if p['record_id'] == d['ID'] and \
               p['redcap_event_name'] == 'Prescreeners':
                if p['adni4_complete']:
                    d['PRID'] = p['redcap_repeat_instance']
                    d['EID'] = '457242'
                    d['PDATE'] = p['prescreener_date2_v2']
                    d['PTYPE'] = 'ADNI4'
                    d['PPAGE'] = 'adni4'
                    d['ADATE'] = p['date_v2_v2_v2_v2_v2']
                elif p['trcds_complete']:
                    d['PRID'] = p['redcap_repeat_instance']
                    d['EID'] = '457242'
                    d['PDATE'] = p['date3_v2_v2']
                    d['PTYPE'] = 'TRC-DS'
                    d['PPAGE'] = 'trcds'
                    d['ADATE'] = p['date1212_v2_v2']
                elif p['abate_complete']:
                    d['PRID'] = p['redcap_repeat_instance']
                    d['EID'] = '457242'
                    d['PDATE'] = p['prescreener_date_abate']
                    d['PTYPE'] = 'ABATE'
                    d['PPAGE'] = 'abate'
                    d['ADATE'] = p['date1212_v2_v2_v2']

        # Append record
        data.append(d)

    if len(data) > 0:
        df = pd.DataFrame(data)
    else:
        df = pd.DataFrame(
            columns=['ID', 'STUDY'])

    df = df.set_index('ID')

    df = df.fillna('')

    return df


def load_prescreeners(rc):
    # Load data as a record per prescreener, allows multiple prescreener
    # records per participant.
    data = []

    records = rc.export_records(
        export_checkbox_labels=True,
        export_blank_for_gray_form_status=True,
        raw_or_label='label',
    )

    # Get prescreener records
    for r in [x for x in records if x['redcap_event_name'] == 'Prescreeners']:
        # Reset
        new_record = {
            'ID': r['record_id'],
            'STATUS': 'TBD'
        }

        if r['adni4_complete']:
            new_record['EID'] = '457242'
            new_record['PDATE'] = r['prescreener_date2_v2']
            new_record['PTYPE'] = 'ADNI4'
            new_record['PPAGE'] = 'adni4'
        elif r['trcds_complete']:
            new_record['EID'] = '457242'
            new_record['PDATE'] = r['date3_v2_v2']
            new_record['PTYPE'] = 'TRC-DS'
            new_record['PPAGE'] = 'trcds'
        elif r['abate_complete']:
            new_record['EID'] = '457242'
            new_record['PDATE'] = r['prescreener_date_abate']
            new_record['PTYPE'] = 'ABATE'
            new_record['PPAGE'] = 'abate'
        else:
            continue

        # Append record
        data.append(new_record)

    # Get info from main record
    for d in data:
        for r in records:
            if d['ID'] != r['record_id']:
                continue

            if r['urp_definition']:
                d['URG'] = r['urp_definition']

            if r['study_name3']:
                d['STUDY'] = r['study_name3']

            # Find the latest status
            if r['status_of_the_screening_vi_3']:
                # Status in this field overrides all
                d['STATUS'] = r['status_of_the_screening_vi_3']
            elif r['recruitment_status']:
                # Use this field otherwise
                d['STATUS'] = r['recruitment_status']

    if len(data) > 0:
        df = pd.DataFrame(data)
    else:
        df = pd.DataFrame(columns=['ID'])

    df = df.set_index('ID')
    df = df.fillna('')

    return df


def load_open(rc):
    data = []

    records = rc.export_records(
        export_checkbox_labels=True,
        export_blank_for_gray_form_status=True,
        raw_or_label='label',
    )

    # Filter to only Unverified, this also excludes blanks
    unverified = [x for x in records if x['study_eligibility_information_complete'] == 'Unverified']
    unsaved = [x for x in records if not x['study_eligibility_information_complete']]

    # process each record id
    for r in unverified:
        # Reset
        new_record = {
            'ID': r['record_id'],
            'STUDY': '',
            'URG': '',
            'STATUS': 'UNKNOWN',
            'NOTES': '',
            'COMPLETE': '',
            'INITIALS': '',
        }

        new_record['STUDY'] = r['study_name3']

        # Find the latest status
        new_record['STATUS'] = r['status_of_the_screening_vi_3']

        if not new_record['STATUS']:
            new_record['STATUS'] = r['recruitment_status']

        if not new_record['STATUS']:
            new_record['STATUS'] = 'TBD'

        new_record['URG'] = r['urp_definition']

        first_name = r['name3_v2']
        last_name = r['last_name_2']

        if first_name and last_name:
            new_record['INITIALS'] = get_initials(first_name, last_name)

        for p in records:
            # Find the prescreeners, select the latest, link it
            if p['record_id'] == new_record['ID'] and p['redcap_event_name'] == 'Prescreeners':
                if p['adni4_complete']:
                    new_record['PRID'] = p['redcap_repeat_instance']
                    new_record['EID'] = '457242'
                    new_record['PDATE'] = p['prescreener_date2_v2']
                    new_record['PTYPE'] = 'ADNI4'
                    new_record['PPAGE'] = 'adni4'
                elif p['trcds_complete']:
                    new_record['PRID'] = p['redcap_repeat_instance']
                    new_record['EID'] = '457242'
                    new_record['PDATE'] = p['date3_v2_v2']
                    new_record['PTYPE'] = 'TRC-DS'
                    new_record['PPAGE'] = 'trcds'
                elif p['abate_complete']:
                    new_record['PRID'] = p['redcap_repeat_instance']
                    new_record['EID'] = '457242'
                    new_record['PDATE'] = p['prescreener_date_abate']
                    new_record['PTYPE'] = 'ABATE'
                    new_record['PPAGE'] = 'abate'

        # Append record
        data.append(new_record)

    for d in data:
        tid = d['ID']

    if len(data) > 0:
        df = pd.DataFrame(data)
    else:
        df = pd.DataFrame(
            columns=['ID', 'STUDY'])

    df = df.set_index('ID')

    df = df.fillna('')

    return df


def get_content(df):
    content = ''

    status_list = df['STATUS'].unique()

    for status in sorted(status_list):
        status_df = df[df.STATUS == status]
        status_content = get_status_content(status_df)
        status_content = STATUS_TEMPLATE.format(len(status_df), status, status_content)
        content += status_content

    content = HTML_TEMPLATE.format('CCM Registry', len(df), content)

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
                study=row['STUDY'],
                status=row['STATUS'],
                initials=row['INITIALS'],
                pid=PID,
            )
        else:
            row_content = ROW_TEMPLATE.format(
                tid=index,
                study=row['STUDY'],
                status=row['STATUS'],
                initials=row['INITIALS'],
                pid=PID,
            )

        if row.get('PDATE', False):
            row_content = row_content[:-5] + PRESCREENER_TEMPLATE.format(
                tid=index,
                ptype=row['PTYPE'],
                ppage=row['PPAGE'],
                rid=row['PRID'],
                eid=row['EID'],
                pid=PID,
                pdate=row['PDATE'],
            ) + '</tr>'

        content += row_content

    return content


def save_data(df, outdir):
    name = 'registry'
    now = datetime.now().strftime("%Y-%m-%d")
    filename = os.path.join(outdir, f'{name}_report_{now}.xlsx')
    if os.path.exists(filename):
        now = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = os.path.join(outdir, f'{name}_report_{now}.xlsx')

    df.to_excel(filename)

    return filename


def make_report(outdir, emailto):
    today = datetime.now().strftime("%Y-%m-%d")

    subject = f'CCM Registry {today}'

    # Get Registry redcap
    rc = get_redcap(PID)

    # Load open records
    df = load_open(rc)

    # Get email content
    content = get_content(df)

    # Email report content
    send_email(content, emailto, subject)

    # Return the report data for saving
    return save_data(df, outdir)
