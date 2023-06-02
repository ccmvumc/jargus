# Monthly Report: CCM Tracking System

# Should all of the forms be repeating instruments? could we have a single
# contact info form that doesn't repeat? and then have the name just appear
# as secondary unique info rather than having multiple name fields?
# and could we have a single repeating form with branching logic for study/versioning?
# and this could all go into the tracking redcap?

# Do we want to count each subject once or 
# multiple if multiple prescreens? doesn't seem to happen very often. so let's
# just count each tracking record once and not care about prescreeners redcap
# at all.

import itertools
import logging
import io
import re
import os
from datetime import datetime, date, timedelta

import pandas as pd
import plotly
import plotly.graph_objs as go
import plotly.subplots
import plotly.express as px
from fpdf import FPDF
from PIL import Image

from ..utils_redcap import get_redcap
from ..utils_email import send_email


logger = logging.getLogger('jargus.reports.Progress')


# STUDY   name_of_the_study_v2_v2
# STATUS  enrollment_status1
# DATE    date_given
# URG     urp_definition


# QA status colors
RGB_GREEN = 'rgb(15,157,88)'
RGB_YELLOW = 'rgb(244,160,0)'
RGB_RED = 'rgb(219,68,55)'
RGB_GREY = 'rgb(155,155,155)'
QASTATUS2COLOR = {
    'Randomized': RGB_GREEN,
    'Screen Fail':  RGB_RED,
    'Lost to followup':  RGB_GREY,
    'In Progress': RGB_YELLOW}

DESCRIPTION = '''
This report summarizes CCM Tracking as a set of plots and tables. Data are pulled and 
merged from multiple CCM Tracking REDCap projects.
'''

STATUSES = '''
Randomized
Lost to Followup
Screen Fail
all others = In Progress
'''

OUTLINE = '''
-Table 
    *all
    *current month
-Timeline 
    *all
    *current month
-Barplots
    *all
    *current month
'''

ALTSTUDY = [
    'which_study',
    'if_yes_what_study_are_they',
    'what_study_are_they_inters',
    'if_yes_what_study'
]


def remap_tracking_study(df):
    df['STUDY'] = df['STUDY'].replace({
        'AHHEAD': 'AHEAD',
        'APOLLO _':'APOLLOE4',
        'APOLLO-E':'APOLLOE4',
        'APOLO-E4':'APOLLOE4',
        'NOVO NOR':'NOVO',
        'TRC-DS S': 'TRC-DS',
        'MIND STU': 'MIND',
        'THE MIND': 'MIND',
        'KIM AND': 'CHANGES',
        'CANCER S': 'NCCR',
        'THE CHAN': 'CHANGES',
        'KIM\'S ST': 'CHANGES',
        'CONSIDER': '',
        'REFERRAL': '',
        'NONE': '',
        'BLAKE WI': '',
        'KIM': 'CHANGES',
        'CHAMP (?': 'CHAMP',
        'CHAMP OR': 'CHAMP',
        'CHAMP ~': 'CHAMP',
        'CHEMOBRA': 'NCCR',
        'INTEREST': '',
        'MIND OR': 'MIND',
        'POSSIBLY': '',
        'THEY ARE': '',
        },
    )
    df['STUDY'] = df['STUDY'].fillna('blank')

    return df


def remap_tracking_status(df):
    df['STATUS'] = df['STATUS'].map({
        'Randomized': 'Randomized',
        'Lost to followup': 'Lost to followup',
        'Screen Fail': 'Screen Fail',
        }
    )
    df['STATUS'] = df['STATUS'].fillna('In Progress')

    return df


def remap_tracking_urg(df):
    df['URG'] = df['URG'].map({
        'Yes': 'URG',
        'No': 'Non-URG',
        '': 'Non-URG',
        }
    )

    df['URG'] = df['URG'].fillna('Non-URG')

    return df


def remap_impair(df):
    df['IMPAIR'] = df['IMPAIR'].map({
        'Yes': 'Impaired',
        'No': 'Not Impaired', 
    })

    df['IMPAIR'] = df['IMPAIR'].fillna('Unknown')

    return df


def load_tracking_data(rc):
    data = []

    records = rc.export_records(
        export_checkbox_labels=True,
        export_blank_for_gray_form_status=True,
        raw_or_label='label',
    )

    record_ids = list(set([x['record_id'] for x in records]))

    # process each record id
    for r in record_ids:
        # Reset
        new_record = {
            'ID': r,
            'STUDY': '',
            'URG': '',
            'STATUS': '',
            'DATE': '',
        }

        # Get data for this record id
        cur_records = [x for x in records if x['record_id'] == r]

        # Load the data from all records including all repeating instruments
        for cur_data in cur_records:
            for k, v in cur_data.items():
                if not v or v == '':
                    # no value found
                    continue
                elif k == 'urp_definition':
                    new_record['URG'] = v
                elif k == 'name_of_the_study_v2_v2':
                    new_record['STUDY'] = v
                elif k == 'enrollment_status1':
                    new_record['STATUS'] = v
                elif k in ['date_given', 'when_is_the_memory_screeni_v2']:
                    if 'DATE' not in new_record:
                        new_record['DATE'] = v
                    elif v > new_record['DATE']:
                        new_record['DATE'] = v
                elif k in ALTSTUDY:
                    # Alternate study fields
                    if not new_record['STUDY']:
                        new_record['STUDY'] = v

             # Standardize the study name
            study = new_record['STUDY']
            study = study.split(',')[0]
            study = study[:8].strip()
            study = study.upper()
            new_record['STUDY'] = study

        # Append record
        data.append(new_record)

    # Return the collected data
    return data


def load_mem_data(rc):
    data = []

    records = rc.export_records(
        export_checkbox_labels=True,
        export_blank_for_gray_form_status=True,
        raw_or_label='label',
    )

    # Then load the memory screening information from repeating
    mem_records = [x for x in records if x['redcap_repeat_instrument'] == 'Memory Screen Information']

    # Only include records with a score
    mem_records = [x for x in records if x['memory_assessment_score_v2']]

    for r in mem_records:
        for a in [
            'what_memory_assessment_did_v2___1', 
            'what_memory_assessment_did_v2___2',
            'what_memory_assessment_did_v2___3']:

            if r[a]:
                # Add record for this mem type
                data.append({
                    'ID': r['record_id'],
                    'DATE': r['when_is_the_memory_screeni_v2'],
                    'ATYPE': r[a],
                    'IMPAIR': r['impaired_v2'],
                })

    # Return the collected data
    return data


class MYPDF(FPDF):
    def set_filename(self, filename):
        self.filename = filename

    def set_project(self, project):
        self.project = project
        today = datetime.now().strftime("%Y-%m-%d")
        self.date = today
        self.title = '{} Monthly Report'.format(project)
        self.subtitle = '{}'.format(datetime.now().strftime("%B %Y"))

    def footer(self):
        self.set_y(-0.35)
        self.set_x(0.5)

        # Write date, title, page number
        self.set_font('helvetica', size=10)
        self.set_text_color(100, 100, 100)
        self.set_draw_color(100, 100, 100)
        self.line(x1=0.2, y1=10.55, x2=8.3, y2=10.55)
        self.cell(w=1, txt=self.date)
        self.cell(w=5, align='C', txt=self.title)
        self.cell(w=2.5, align='C', txt=str(self.page_no()))


def blank_letter():
    p = MYPDF(orientation="P", unit='in', format='letter')
    p.set_top_margin(0.5)
    p.set_left_margin(0.5)
    p.set_right_margin(0.5)
    p.set_auto_page_break(auto=False, margin=0.5)

    return p


def make_pdf(info, filename):
    logger.debug('making PDF')

    # Initialize a new PDF letter size and shaped
    pdf = blank_letter()
    pdf.set_filename(filename)
    pdf.set_project('CCM Tracking')

    add_first_page(pdf, info)

    # Counts
    logger..debug('adding count pages')
    add_count_pages(pdf, info['tracking'])

    # Timeline
    logger.debug('adding timeline page')
    add_timeline_page(pdf, info['tracking'])

    # QA
    logger.debug('adding qa page')
    add_qa_page(pdf, info['tracking'])

    # Memory Screenings
    logger.debug('add memory screening page')
    add_mem_page(pdf, info['mem'])

    # Last page
    add_last_page(pdf, info)

    # Save to file
    logger.debug('saving PDF to file:{}'.format(pdf.filename))
    try:
        pdf.output(pdf.filename)
    except Exception as err:
        logger.error('error while saving PDF:{}:{}'.format(pdf.filename, err))

    return True


def add_first_page(pdf, info):
    # Start the page with titles
    pdf.add_page()
    pdf.set_font('helvetica', size=22)
    pdf.cell(w=7.5, h=0.4, align='C', txt=pdf.title)
    pdf.ln(0.4)
    pdf.cell(w=7.5, h=0.4, align='C', txt=pdf.subtitle, border='B')
    pdf.ln(0.4)

    pdf.set_font('helvetica', size=12)
    pdf.multi_cell(w=7.5, h=0.3, txt=DESCRIPTION)

    pdf.ln(0.4)
    pdf.set_font('helvetica', size=20, style="B")
    pdf.cell(w=6, h=0.1, align='C', txt='Outline')
    pdf.ln(0.1)
    pdf.set_font('helvetica', size=16)
    pdf.multi_cell(w=6, h=0.3, txt=OUTLINE)

    pdf.ln(0.2)
    pdf.set_font('helvetica', size=20, style="B")
    pdf.cell(w=6, h=0.1, align='C', txt='Statuses')
    pdf.ln(0.1)
    pdf.set_font('helvetica', size=16)
    pdf.multi_cell(w=6, h=0.3, txt=STATUSES)

    return pdf


def add_last_page(pdf, info):
    today = date.today()
    txt = f'\n{today} Created by ccmutils/run_tracking_monthly_report.py\n\n'

    total = 0
    for pid in ['155254', '131007', '96194', '162609']:
        rc = get_redcap(pid)
        cur = len(rc.export_records(fields=['record_id']))
        total += cur
        txt += f'\n{cur}\t {pid}\t {rc.export_project_info().get("project_title")}\n'

    txt += f'\n\nTotal={total}\n\n'

    # Start the page with titles
    pdf.add_page()
    pdf.set_font('helvetica', size=12)
    pdf.multi_cell(w=7.5, h=0.3, txt=txt)

    return pdf


def add_count_pages(pdf, df):
    # Start a new page
    pdf.add_page()

    # Show all counts
    pdf.set_font('helvetica', size=18)
    pdf.cell(w=7.5, h=0.4, align='C', txt='')
    pdf.ln(0.25)
    plot_counts(pdf, df)
    pdf.ln(1)

    if len(df.STUDY.unique()) > 3:
        # Start a new page so it fits
        pdf.add_page()

    # Show counts in date range
    pdf.cell(w=7.5, h=0.4, align='C', txt='')
    pdf.ln(0.25)
    plot_counts(pdf, df, rangetype='lastmonth')
    pdf.ln(1)

    return pdf


def add_qa_page(pdf, df):

    # Get the dates of last month
    enddate = date.today().replace(day=1) - timedelta(days=1)
    startdate = date.today().replace(day=1) - timedelta(days=enddate.day)

    # Get the name of last month
    lastmonth = startdate.strftime("%B")

    all_image = plot_qa(df)
    cur_image = plot_qa(df, startdate, enddate)

    pdf.add_page()
    pdf.set_font('helvetica', size=18)
    pdf.cell(w=7.5, align='C', txt='All')

    pdf.image(all_image, x=0.5, y=0.8, w=7.5)
    pdf.ln(5)

    pdf.cell(w=7.5, align='C', txt=f'{lastmonth}')
    pdf.image(cur_image, x=0.5, y=5.9, w=7.5)

    return pdf


def add_timeline_page(pdf, df):  
    pdf.add_page()
    pdf.set_font('helvetica', size=18)

    # Draw all timeline
    _txt = 'All Timeline'
    pdf.cell(w=7.5, align='C', txt=_txt)
    image = plot_timeline(df)
    pdf.image(image, x=0.5, y=0.75, w=7.5)
    pdf.ln(5)

    # Get the dates of last month
    enddate = date.today().replace(day=1) - timedelta(days=1)
    startdate = date.today().replace(day=1) - timedelta(days=enddate.day)

    # Get the name of last month
    lastmonth = startdate.strftime("%B")

    _txt = f'{lastmonth} Timeline'
    image = plot_timeline(df, startdate=startdate, enddate=enddate)
    pdf.cell(w=7.5, align='C', txt=_txt)
    pdf.image(image, x=0.5, y=5.75, w=7.5)
    pdf.ln()

    return pdf


def add_mem_page(pdf, df):
    pdf.add_page()

    # Show all counts
    pdf.set_font('helvetica', size=18)
    pdf.cell(w=7.5, h=0.4, align='C', txt='')
    pdf.ln(0.25)
    plot_mem(pdf, df)
    pdf.ln()

    # Show counts in date range
    pdf.cell(w=7.5, h=0.4, align='C', txt='')
    plot_mem(pdf, df, rangetype='lastmonth')

    return pdf


def plot_counts(pdf, df, rangetype=None):
    status_list = sorted(df.STATUS.unique())
    study_list = sorted(df.STUDY.unique())
    #print(status_list)
    #print(study_list)

    if rangetype == 'lastmonth':
        pdf.set_fill_color(114, 172, 77)

        # Get the dates of lst month
        _end = date.today().replace(day=1) - timedelta(days=1)
        _start = date.today().replace(day=1) - timedelta(days=_end.day)

        # Get the name of last month
        lastmonth = _start.strftime("%B")

        # Filter the data to last month
        df = df[df.DATE >= _start.strftime('%Y-%m-%d')]
        df = df[df.DATE <= _end.strftime('%Y-%m-%d')]

        # Create the lastmonth header
        _txt = f'{lastmonth} Counts (URG)'
    else:
        pdf.set_fill_color(94, 156, 211)
        _txt = 'All Counts (URG)'

    # Draw heading
    pdf.set_font('helvetica', size=12)
    pdf.cell(w=7.5, h=0.5, txt=_txt, align='C', border=0)
    pdf.ln(0.4)

    # Header Formatting
    pdf.cell(w=1.0)
    pdf.set_text_color(245, 245, 245)
    pdf.set_line_width(0.01)
    _kwargs = {'w': 1.3, 'h': 0.5, 'border': 1, 'align': 'C', 'fill': True}

    pdf.cell(w=0.3, border=0, fill=False)

    # Column header for each session type
    for cur_status in status_list:
        _color = QASTATUS2COLOR[cur_status]
        _r, _g, _b = _color[4:-1].split(',')
        #print(_r, _g, _b)
        pdf.set_fill_color(int(_r), int(_g), int(_b))
        pdf.cell(**_kwargs, txt=cur_status)

    # Totals column header
    pdf.set_fill_color(255, 255, 255)
    pdf.set_text_color(0, 0, 0)
    _kwargs_tot = {'w': 1.0, 'h': 0.5, 'border': 1, 'align': 'C', 'fill': False}
    pdf.cell(**_kwargs_tot, txt='TOTAL')

    # Got to next line
    pdf.ln()

    # Row formatting
    pdf.set_fill_color(255, 255, 255)
    pdf.set_text_color(0, 0, 0)
    _kwargs = {'w': 1.3, 'h': 0.5, 'border': 1, 'align': 'C', 'fill': False}
    _kwargs_site = {'w': 1.3, 'h': 0.5, 'border': 1, 'align': 'C', 'fill': False}
    _kwargs_tot = {'w': 1.0, 'h': 0.5, 'border': 1, 'align': 'C', 'fill': False}

    # Row for each study
    for cur_study in sorted(study_list):
        dfs = df[df.STUDY == cur_study]
        dfsu = dfs[dfs.URG == 'URG']
        _txt = cur_study

        if len(dfs) == 0:
            continue

        pdf.cell(**_kwargs_site, txt=_txt)

        # Count each status
        for cur_status in status_list:
            cur_count = str(len(dfs[dfs.STATUS == cur_status]))

            cur_urg = str(len(dfsu[dfsu.STATUS == cur_status]))
            if cur_urg != '0':
                cur_count = f'{cur_count}({cur_urg})'

            pdf.cell(**_kwargs, txt=cur_count)

        # Total for row
        cur_count = str(len(dfs))
        pdf.cell(**_kwargs_tot, txt=cur_count)
        pdf.ln()

    # TOTALS row
    pdf.cell(w=1.0)
    pdf.cell(w=0.3, h=0.5)
    for cur_status in status_list:
        pdf.set_font('helvetica', size=18)
        cur_count = str(len(df[df.STATUS == cur_status]))
        pdf.cell(**_kwargs, txt=cur_count)

    pdf.cell(**_kwargs_tot, txt=str(len(df)))

    pdf.ln()

    pdf.set_font('helvetica', size=8)
    pdf.cell(w=7.5, h=0.5, txt='Total count includes URG count, Total Count(URG Count)')

    return pdf


def plot_timeline(df, startdate=None, enddate=None):
    status_list = df.STATUS.unique()
    urg_list = df.URG.unique()

    fig = plotly.subplots.make_subplots(rows=1, cols=1)
    fig.update_layout(margin=dict(l=40, r=40, t=40, b=40))

    df = df.sort_values('STUDY', ascending=False)

    for status in status_list:

        _color = QASTATUS2COLOR[status]

        for urg in urg_list:

            # Get subset
            dfs = df[(df.STATUS == status) & (df.URG == urg)]
            if dfs.empty:
                continue

            if startdate:
                dfs = dfs[dfs.DATE >= startdate.strftime('%Y-%m-%d')]

            if enddate:
                dfs = dfs[dfs.DATE <= enddate.strftime('%Y-%m-%d')]

            # Nothing to plot so go to next
            if dfs.empty:
                logger.debug('nothing to plot:{}:{}'.format(urg, status))
                continue

            # markers symbols, see https://plotly.com/python/marker-style/
            if urg == 'URG':
                symb = 'star-dot'
            else:
                symb = 'circle-dot'

            # Convert hex to rgba with alpha of 0.5
            if _color.startswith('#'):
                _rgba = 'rgba({},{},{},{})'.format(
                    int(_color[1:3], 16),
                    int(_color[3:5], 16),
                    int(_color[5:7], 16),
                    0.7)
            else:
                _r, _g, _b = _color[4:-1].split(',')
                _a = 0.7
                _rgba = 'rgba({},{},{},{})'.format(_r, _g, _b, _a)

            # Plot this type
            try:
                _row = 1
                _col = 1
                fig.append_trace(
                    go.Box(
                        name='{} {} ({})'.format(status, urg, len(dfs)),
                        x=dfs['DATE'],
                        y=dfs['STUDY'],
                        boxpoints='all',
                        jitter=0.7,
                        text=dfs['ID'],
                        pointpos=0.5,
                        orientation='h',
                        marker={
                            'symbol': symb,
                            'color': _rgba,
                            'size': 12,
                            'line': dict(width=2, color=_color)
                        },
                        line={'color': 'rgba(0,0,0,0)'},
                        fillcolor='rgba(0,0,0,0)',
                        hoveron='points',
                    ),
                    _row,
                    _col)
            except Exception as err:
                logger.error(err)
                return None

    # show lines so we can better distinguish categories
    fig.update_yaxes(showgrid=True)

    # Set the size
    fig.update_layout(width=900)

    # Export figure to image
    _png = fig.to_image(format="png")
    image = Image.open(io.BytesIO(_png))
    return image


def plot_qa(df, startdate=None, enddate=None):

    if startdate:
        df = df[df.DATE >= startdate.strftime('%Y-%m-%d')]

    if enddate:
        df = df[df.DATE <= enddate.strftime('%Y-%m-%d')]

    # Initialize a figure
    fig = plotly.subplots.make_subplots(rows=1, cols=1)
    fig.update_layout(margin=dict(l=40, r=40, t=40, b=40))

    dfp = df.pivot_table(
        index='STUDY',
        columns='STATUS',
        values='ID',
        aggfunc=pd.Series.nunique,
        fill_value=0)

    # Draw bar for each status, these will be displayed in order,
    # ydata should be the types, xdata should be count of status
    # for each type
    for cur_status, cur_color in QASTATUS2COLOR.items():
        ydata = dfp.index
        if cur_status not in dfp:
            xdata = [0] * len(dfp.index)
        else:
            xdata = dfp[cur_status]

        cur_name = '{} ({})'.format(cur_status, sum(xdata))

        fig.append_trace(
            go.Bar(
                x=ydata,
                y=xdata,
                name=cur_name,
                marker=dict(color=cur_color),
                opacity=0.9),
            1, 1)

    # Customize figure
    fig['layout'].update(barmode='stack', showlegend=True, width=900)

    # Export figure to image
    _png = fig.to_image(format="png")
    image = Image.open(io.BytesIO(_png))

    return image


def plot_mem(pdf, df, rangetype=None):
    # df columns: ID, DATE, ATYPE, IMPAIR

    if rangetype == 'lastmonth':
        pdf.set_fill_color(114, 172, 77)

        # Get the dates of lst month
        _end = date.today().replace(day=1) - timedelta(days=1)
        _start = date.today().replace(day=1) - timedelta(days=_end.day)

        # Get the name of last month
        lastmonth = _start.strftime("%B")

        # Filter the data to last month
        df = df[df.DATE >= _start.strftime('%Y-%m-%d')]
        df = df[df.DATE <= _end.strftime('%Y-%m-%d')]

        # Create the lastmonth header
        _txt = f'{lastmonth} Memory Screenings'
    else:
        pdf.set_fill_color(94, 156, 211)
        _txt = 'All Memory Screenings'

    # Draw heading
    pdf.ln()
    pdf.set_font('helvetica', size=14)
    pdf.cell(w=7.5, h=0.5, txt=_txt, align='C', border=0)
    pdf.ln(0.4)

    # Header Formatting
    pdf.cell(w=1.0)
    pdf.set_text_color(245, 245, 245)
    pdf.set_line_width(0.01)
    _kwargs = {'w': 1.5, 'h': 0.5, 'border': 1, 'align': 'C', 'fill': True}

    pdf.cell(w=0.5, border=0, fill=False)

    # Column headers
    for cur_status in sorted(df.IMPAIR.unique()):
        pdf.cell(**_kwargs, txt=cur_status)

    # Totals column header
    pdf.set_fill_color(255, 255, 255)
    pdf.set_text_color(0, 0, 0)
    _kwargs_tot = {'w': 1.0, 'h': 0.5, 'border': 1, 'align': 'C', 'fill': False}
    pdf.cell(**_kwargs_tot, txt='TOTAL')

    # Got to next line
    pdf.ln()

    # Row formatting
    pdf.set_fill_color(255, 255, 255)
    pdf.set_text_color(0, 0, 0)
    _kwargs = {'w': 1.5, 'h': 0.5, 'border': 1, 'align': 'C', 'fill': False}
    _kwargs_site = {'w': 1.5, 'h': 0.5, 'border': 1, 'align': 'C', 'fill': False}
    _kwargs_tot = {'w': 1.0, 'h': 0.5, 'border': 1, 'align': 'C', 'fill': False}

    # Row for each mem type
    for cur_type in sorted(df.ATYPE.unique()):
        dft = df[df.ATYPE == cur_type]
        _txt = cur_type

        if len(dft) == 0:
            continue

        pdf.cell(**_kwargs_site, txt=_txt)

        # Counts of each status for thie mem type
        for cur_status in sorted(df.IMPAIR.unique()):
            cur_count = str(len(dft[dft.IMPAIR == cur_status]))
            pdf.cell(**_kwargs, txt=cur_count)

        # Total for row
        cur_count = str(len(dft))
        pdf.cell(**_kwargs_tot, txt=cur_count)
        pdf.ln()

    # TOTALS row
    pdf.cell(w=1.0)
    pdf.cell(w=0.5, h=0.5)
    for cur_status in sorted(df.IMPAIR.unique()):
        pdf.set_font('helvetica', size=18)
        cur_count = str(len(df[df.IMPAIR == cur_status]))
        pdf.cell(**_kwargs, txt=cur_count)

    pdf.cell(**_kwargs_tot, txt=str(len(df)))

    pdf.ln()

    return pdf


def make_report(outdir, emailto):
    email_subject = 'CCM Tracking Progress Report'
    info = {}

    # Load tracking data
    tracking_data = pd.DataFrame(
        load_tracking_data(get_redcap('155254')) + \
        load_tracking_data(get_redcap('131007')) + \
        load_tracking_data(get_redcap('162609')) + \
        load_tracking_data(get_redcap('96194')))

    # Remap column values
    tracking_data = remap_tracking_status(tracking_data)
    tracking_data = remap_tracking_study(tracking_data)
    tracking_data = remap_tracking_urg(tracking_data)

    # this resulted in empty set
    #tracking_data['DATE'] = tracking_data['DATE'].fillna('2018-01-01')
    #print(len(tracking_data[tracking_data['DATE'] == '2018-01-01']))

    # Load memory screens
    mem_data = pd.DataFrame(load_mem_data(get_redcap('155254')))
    mem_data = remap_impair(mem_data)

    # Make the PDF
    info['tracking'] = tracking_data
    info['mem'] = mem_data
    filename = os.path.join(outdir, 'CCM_tracking_monthly.pdf')
    make_pdf(info, filename)

    # Email the pdf as attachment
    send_email(filename, emailto, email_subject, pdf=filename)

    return filename
