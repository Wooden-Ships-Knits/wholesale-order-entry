import pandas as pd

from . import fetch as dto
from app.config import settings

def rep_name(reps):
    if len(reps) == 0:
        return ""
    elif len(reps) == 1:
        return reps[0]
    elif len(reps) == 2:
        return f"{reps[0]} and {reps[1]}"
    else:
        return ", ".join(reps[:-1]) + f", and {reps[-1]}"

def total_UA(df, reps, wholesale):
    total_units = 0
    total_amounts = 0

    for r in reps:
        rows = df[df["Sales Territory"] == r]

        for col in wholesale:
            for val in rows[col]:
                parts = str(val).split()
                if len(parts) >= 2:
                    total_units += int(float(parts[0]))
                    total_amounts += float(parts[1].replace("$", "").replace(",", ""))

    return total_units, total_amounts

def breakdown(df, reps, campaigns, wholesale):
    lines = []

    for i, r in enumerate(reps, 1):
        rows = df[df["Sales Territory"] == r]

        rep_lines = []

        for col in wholesale:
            season = col.split()[0]  # "F26" from "F26 Wholesale"

            total_units = 0
            total_amount = 0

            for val in rows[col]:
                parts = str(val).split()
                if len(parts) >= 2:
                    total_units += int(float(parts[0]))
                    total_amount += float(parts[1].replace("$", "").replace(",", ""))

            # only show if there is data
            if total_units > 0 or total_amount > 0:
                amount_str = f"${total_amount:,.2f}"
                rep_lines.append(f"* {season}: {total_units} pcs, {amount_str}")

        text = (
            f"{i}. {r} ({campaigns[i-1]})\n" +
            "\n".join(rep_lines)
        )

        lines.append(text)

    return "\n\n".join(lines)



def run() -> dict:
    """Build the DTO recap. Returns {"recap": str, "log": [str, ...]} — no file
    I/O, so the admin page can hold the last run in memory and re-show it without
    re-running (Option A)."""
    log = []

    report_id = dto.report()
    log.append(f"Loaded Salesforce report '{settings.dto_report_name}' (id {report_id}).")

    df = dto.run_matrix(report_id)

    reps = [d for d in df["Sales Territory"] if pd.notna(d) and d != "Grand Total"]
    campaigns = [d for d in df["Campaign"] if d not in ("Subtotal", "Grand Total")]
    wholesale = [col for col in df.columns if str(col).endswith("Wholesale")]
    log.append(f"{len(reps)} territories, {len(wholesale)} price book(s).")

    sum_units, sum_amounts = total_UA(df, reps, wholesale)
    sum_amounts_str = f"${sum_amounts:,.2f}"
    log.append(f"Total today: {sum_units} pcs, {sum_amounts_str}.")

    reps_only = []
    for r in reps:
        # Some territories are formatted "XX - Name"; others have no "-".
        parts = r.split("-", 1)
        name = parts[1].strip() if len(parts) > 1 else parts[0].strip()
        reps_only.append(name.split(" ")[0])

    if sum_amounts > 10000:
        text = f"""Hi {settings.dto_recap_recipient},

We want to inform you that today we received orders over $10k in total from {rep_name(reps_only)}. The total qty of today's order is {sum_units} pcs with a total amount of {sum_amounts_str}.

Below is the breakdown:

{breakdown(df, reps, campaigns, wholesale)}

Thanks!
"""
    else:
        text = f"Less than 10k. With total qty of today's order is {sum_units} pcs with a total amount of {sum_amounts_str}."

    return {"recap": text.strip(), "log": log}

if __name__ == "__main__":
    import json

    print(json.dumps(run(), indent=2))