import pandas as pd

from app.config import settings
from app.salesforce.client import _client


def report():
    """
    Customer Recap - ALL -> flat detail table (seperti 'Export Details').
    Dijalankan per Sales Territory utk lewatin cap 2000 baris API sync.
    """
    sf = _client()  # shared, already-authenticated session (fetched per call)
    rpt = sf.query(f"SELECT Id FROM Report WHERE Name = '{settings.dto_report_name}'")
    report_id = rpt['records'][0]['Id']

    return report_id
    
def run_matrix(report_id):
    """Run the matrix report and return a DataFrame shaped like the old
    HTML-export df, so the existing total_UA/breakdown code works unchanged:

      - columns: 'Sales Territory', 'Campaign', one '<season> Wholesale' per price book
      - each wholesale cell is a single '<units> $<amount>' string, e.g. '18.0000 $1,252.00'
      - subtotal rows: Sales Territory = NaN, Campaign = 'Subtotal'
      - last row: Sales Territory = Campaign = 'Grand Total'
    """
    sf     = _client()
    rep    = sf.restful(f'analytics/reports/{report_id}')
    fact   = rep['factMap']
    across = rep['groupingsAcross']['groupings']        # price books: F26 Wholesale, S26 Wholesale
    down   = rep['groupingsDown']['groupings']          # territories -> campaigns

    def cells(down_key):
        """'<units> $<amount>' string per price-book column for a factMap down key."""
        vals = {}
        for col in across:
            agg    = fact[f"{down_key}!{col['key']}"]['aggregates']
            units  = agg[0]['value'] or 0
            amount = agg[1]['value'] or 0
            vals[col['label']] = f"{units:.4f} ${amount:,.2f}"
        return vals

    rows = []
    for terr in down:                                  # level 0: Sales Territory
        for camp in terr['groupings']:                 # level 1: Campaign (key like "0_0")
            rows.append({'Sales Territory': terr['label'],
                         'Campaign': camp['label'],
                         **cells(camp['key'])})
        # territory subtotal: blank territory so reps/total_UA ignore it
        rows.append({'Sales Territory': float('nan'),
                     'Campaign': 'Subtotal',
                     **cells(terr['key'])})

    # grand total
    rows.append({'Sales Territory': 'Grand Total',
                 'Campaign': 'Grand Total',
                 **cells('T')})

    return pd.DataFrame(rows)
