"""Builds the DMM recap text from the Salesforce report + the two sheets."""
from datetime import date, datetime

import pandas as pd

from app.config import settings

from . import email_schedule as es
from . import fetch as udmm
from . import problem_list_reps as plp

def add_mode(group):
    parts  = group.split(" ")
    prefix = " ".join(parts[:-3])          # "April 2026 S26 SWEATERS"
    rng    = " ".join(parts[-3:])          # "04/01 - 04/30"
    mode   = 'FCL' if parts[-1].endswith('15') else 'AIR'   # end day 15 -> FCL
    return f'{prefix} {mode} {rng}'

def genText():
    #====================== part one
    jumlah, shiipping_plan = plp.problemListReps()

    SO_total = 'SOs' if jumlah > 1 else 'SO'
    col = 'Planned Ship Date\n(Bali time)'

    ship_on = ""
    for ship_date, row in shiipping_plan.iterrows():
        d = datetime.strptime(ship_date.strip(), '%a, %b %d').replace(year=date.today().year).date()
        lt = (d - date.today()).days
        nice_date = d.strftime('%A, %B ') + str(d.day)   # 'Wednesday, July 1'
        ship_on += f"""
* For {row['SO qty']} {SO_total}, we plan to ship on {nice_date} (LT = {lt} days)"""
    paragraphOne = f"""
Hi {settings.dmm_recap_recipient},

Please see below the Daily Morning Meeting Update - {pd.Timestamp(date.today()).strftime('%A, %B %d, %Y')}.

Confirming, today we had a daily morning meeting as scheduled.

Today, we have a total of {jumlah} {SO_total} that have been paid {ship_on}

Confirming that there are no charged orders from more than 3 days that have not yet shipped.

Additionally, below is the total of the open orders that remain unpaid as of today."""
    
    #======================= part two
    # report() returns formatted display strings ('$1,068.00', '16.0000') to match the
    # SF UI, so parse the numeric columns back to numbers before aggregating.
    df = udmm.report()
    # '01-08 FCL' + 'S26 SWEATERS 06/01 - 06/30' -> 'FCL S26 SWEATERS (06/01 - 06/30)'
    # drop the leading ship-date prefix, wrap the trailing date range in parens
    df['Unpaid Group'] = (df['Estimated Shipment Name'] + ' ' + df['Order Name']).str.replace(
        r'^\d{2}-\d{2} (.*) (\d{2}/\d{2} - \d{2}/\d{2})$', r'\1 (\2)', regex=True)
    
    df['Product Amount'] = df['Product Amount'].replace(r'[$,]', '', regex=True).astype(float)
    df['Total Units']    = df['Total Units'].astype(float)

    # One row per Unpaid Group: count SOs, sum units and amount. (sort=False keeps SF order)
    df = (df.groupby('Unpaid Group', sort=False)
            .agg(**{'# of SO':        ('Order: Order Number', 'count'),
                    'Total Units':    ('Total Units', 'sum'),
                    'Product Amount': ('Product Amount', 'sum')})
            .reset_index())

    # Email label: put the month name first -> '<Month> <MODE> (<range>)'  e.g. 'April AIR (04/01 - 04/30)'
    mode  = df['Unpaid Group'].str.split().str[0]                                   # 'AIR' / 'FCL'
    rng   = df['Unpaid Group'].str.extract(r'\((\d{2}/\d{2} - \d{2}/\d{2})\)')[0]   # '04/01 - 04/30'
    month = pd.to_datetime(rng.str[:5], format='%m/%d').dt.strftime('%B')           # '04/01' -> 'April'
    df['Label'] = month + ' ' + mode + ' (' + rng + ')'

    # Order the unpaid groups chronologically by month (range start, e.g. '04/01' -> April).
    df = df.assign(_month_order=pd.to_datetime(rng.str[:5], format='%m/%d'))
    df = df.sort_values('_month_order', kind='stable').reset_index(drop=True)

    unpaid_text = ""

    for idx, d in df.iterrows():
        # Latest email sent on/before today for this ship window (past month -> follow-up #7,
        # ongoing month -> closest sent date). Blank if the window isn't in the Email Schedule.
        sent_line = es.sentEmailLine(d['Label'])
        email_text = f"\n    * {sent_line}" if sent_line else ""
        unpaid_text +=f"""
    UNPAID {d['Label']} order:
    * # of SO: {d['# of SO']} SO, TTL QTY: {int(d['Total Units'])}, TTL Amount: ${int(d['Product Amount']):,}{email_text}
    """

    paragraphTwo = f"""
    {unpaid_text}
    Thanks!
    """
    paragraph_combined = paragraphOne + paragraphTwo
    return paragraph_combined