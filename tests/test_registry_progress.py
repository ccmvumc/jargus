from datetime import datetime
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

from jargus.reports.registry import get_redcap, PID, load_all


filename = 'test.pdf'

plt.style.use('seaborn-v0_8-darkgrid')


def months_since(row_date, today):
    y = today.year - row_date.year
    m = today.month - row_date.month
    d = today.day - row_date.day
    days_in_month = pd.Period(row_date.strftime('%Y-%m')).days_in_month

    print(today, y, m, d, days_in_month)

    return (int(y) * 12) + int(m) + (int(d) / days_in_month)


def add_page1(df, pdf):
    fig, ax = plt.subplots(2, 1, figsize=(8.5, 11))
    fig.suptitle('CCM Recruitment Report', fontsize=16, weight='bold')

    # Bar plot of prescreener counts per study

    # Pivot to count per study
    dfp = df.groupby('STUDY').size()

    # Get distinct color for each study
    _col = [f'C{c}' for c in range(0, len(dfp))]

    # TBD: filter to last 30 days
    _title = 'Prescreeners'
    dfp.plot(kind='bar', ax=ax[0], color=_col, rot=0, xlabel='', title=_title)

    # Bar plot of prescreener counts by status, stacked by study
    dfp = df.copy()[~df.STATUS.isin([
        'Not Eligible for Screening Visit',
        'No Longer Interested in Participating',
        'TBD',
        'Scheduled'
    ])]
    dfp = dfp.groupby('STATUS')['STUDY'].value_counts().unstack(level=1)
    _title = 'Current Status of Active Prescreeners'
    dfp.plot.bar(stacked=True, ax=ax[1], rot=0, title=_title, xlabel='')
    plt.xticks(wrap=True, fontsize=10)

    labels = [f'{i:.0f}' for i in dfp.to_numpy().flatten(order='F')]
    for i, patch in enumerate(ax[1].patches):
        if not labels[i] or labels[i] == 'nan':
            continue

        x, y = patch.get_xy()
        x += patch.get_width() / 2
        y += patch.get_height() / 2
        ax[1].annotate(labels[i], (x, y), ha='center', va='center', c='white')

    pdf.savefig(fig, dpi=300, pad_inches=1)


def add_page2(df, pdf):
    fig, ax = plt.subplots(2, 1, figsize=(8.5, 11))

    waiters = df[df.STATUS == 'Attempting to Schedule']
    waiters = waiters[waiters.ADATE.ne('')]

    # Get months column
    waiters['DATE'] = pd.to_datetime(waiters['ADATE'])
    now = datetime.now()
    waiters['MONTHS'] = waiters['DATE'].apply(lambda x: months_since(x, now))
    waiters['MONTHS'] = waiters['MONTHS'].astype(int).astype(str)
    print(waiters)

    # Make the plot
    _title = 'How long have they been waiting?'
    dfp = waiters.groupby('MONTHS')['STUDY'].value_counts().unstack(level=1)
    dfp.plot.bar(stacked=True, ax=ax[0], rot=0, title=_title)

    # Source of lead plot
    sources = df[df.SOURCE.ne('')]

    sources['SOURCE'] = sources['SOURCE'].replace({
        'Physician Referral': 'Physician\nReferral',
        'Recruitment Event': 'Recruitment\nEvent',
    })
    dfp = sources.groupby('SOURCE')['STUDY'].value_counts().unstack(level=1)
    _title = 'How did they hear about our studies?'
    dfp.plot.bar(stacked=True, ax=ax[1], rot=0, title=_title)

    # Print the page to pdf
    pdf.savefig(fig, dpi=300, pad_inches=1)


def add_page3(df, pdf):
    fig, ax = plt.subplots(2, 1, figsize=(8.5, 11))

    # Memory Screenings Table
    mem = df[df.MSCORE.ne('')]
    dfp = mem.groupby('MTYPE')['MRESULT'].value_counts().unstack(level=1).fillna('')

    ax[0].axis('off')
    ax[0].axis('tight')

    table = ax[0].table(
        dfp.values,
        colLabels=dfp.columns,
        rowLabels=dfp.index,
        loc='center',
    )
    table.set_fontsize(14)
    table.scale(.5, 4)

    ax[0].set_title('Memory Screenings')

    ax[1].axis('off')
    ax[1].set_title('Memory Screenings (monthly)')

    # Print the page to pdf
    pdf.savefig(fig, dpi=300, pad_inches=1)


def add_page4(df, pdf):
    fig, ax = plt.subplots(2, 1, figsize=(8.5, 11))

    # Prescreener Status Table

    # Print the page to pdf
    pdf.savefig(fig, dpi=300, pad_inches=1)


def add_page5(df, pdf):
    fig, ax = plt.subplots(2, 1, figsize=(8.5, 11))
    # Prescreener status counts stacked bar by project, color=status

    # Timeline

    # Print the page to pdf
    pdf.savefig(fig, dpi=300, pad_inches=1)


df = load_all(get_redcap(PID))

df['URG'] = df['URG'].replace('', 'No')
df['STUDY'] = df['STUDY'].str.upper()

df['STATUS'] = df['STATUS'].replace({
    'Attempting to Schedule Screening Visit': 'Attempting to Schedule',
    'Pending Approval by the PI': 'Pending PI Approval',
    'Yes, Approved by the clinician': 'PI approved',
    'On Wait List': 'Waitlist',
})


print(df.STATUS.unique())
print(df.SOURCE.unique())
print(df.SOURCE2.unique())


with PdfPages(filename) as pdf:
    add_page1(df, pdf)
    add_page2(df, pdf)
    add_page3(df, pdf)
    add_page4(df, pdf)
    add_page5(df, pdf)

    # Finish up
    #plt.close()
