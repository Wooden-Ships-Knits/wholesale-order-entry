"""DMM entry point for /api/admin/reports/dmm — same contract as the DTO recap.

Gathers the recap's data, then text_gen lays it out:

  Paid      "WHOLESALE Paid Open Orders" rows updated today; AIR/FCL from each
            SO's Estimated Shipment Name in Salesforce.
  Unpaid    the Salesforce "UNPAID DAILY MORNING MEETING" report, grouped by
            season + AIR/FCL + ship window.
            Each window's last/next email comes from the "Email Schedule" tab.
            A window not on it falls back to its orders' own dates on the
            month tab ("OCT", "NOV", …).
  Accounts  FCL windows, and windows whose schedule has no email left before
            the cancel date, list every account instead of a Plan: its latest
            problem note (rep tabs) and its own last/next email (month tab).
            Decided 2026-10-27.
"""
from __future__ import annotations

from app.config import settings
from app.reports.clock import today

from . import email_schedule, fetch, order_tabs, problem_list_reps, rep_notes, text_gen
from .steps import nearest, parse


def rep_short(territory: str) -> str | None:
    """'FL - Jason Hilsenrad' -> 'Jason'; House territories -> 'House'."""
    if not territory.strip():
        return None
    if " - " not in territory:
        return "House"  # e.g. 'AK / AZ / NE / NV'
    name = territory.rsplit(" - ", 1)[1].split()
    return name[0] if name else None


def run() -> dict:
    """Build the DMM recap. Returns {"recap": str, "log": [str, ...]}."""
    day = today()
    log = [
        f"Today: {day:%a, %b %d %Y} ({settings.report_timezone}).",
        f"Salesforce report: {settings.dmm_report_name!r}, Date Required up to {fetch.window_end(day):%Y-%m-%d}.",
    ]

    paid_rows = problem_list_reps.paid_today(day)
    unpaid = fetch.report(day)
    schedule = email_schedule.Schedule.load(day)

    # ---- unpaid groups
    by_group: dict[tuple, list[fetch.Unpaid]] = {}
    for u in unpaid:
        key = email_schedule.range_key(u.order_name)
        if key is None:
            log.append(f"Skipped {u.number} ({u.order_name!r}): no ship window in its Order Name.")
            continue
        window = f"{key[0]:02d}/{key[1]:02d} - {key[2]:02d}/{key[3]:02d}"
        season = u.order_name.split()[0] if u.order_name.split() else ""
        by_group.setdefault((season, fetch.mode(u.shipment), window, key), []).append(u)

    groups: list[tuple[text_gen.Group, list[fetch.Unpaid], email_schedule.Status | None]] = []
    for (season, mode, window, key), rows in by_group.items():
        status = schedule.status(window)
        g = text_gen.Group(
            season=season, mode=mode, window=window,
            start=nearest(key[0], key[1], day),
            sos=len(rows), qty=sum(r.units for r in rows), amount=sum(r.amount for r in rows),
        )
        if mode == "FCL" or (status and status.ended):
            g.accounts = []
        groups.append((g, rows, status))

    # ---- sheet + Salesforce details, only for the orders that need them
    month_tabs: dict[int, dict[str, order_tabs.OrderSteps]] = {}

    def tab_for(g: text_gen.Group) -> dict[str, order_tabs.OrderSteps]:
        if g.start.month not in month_tabs:
            month_tabs[g.start.month] = order_tabs.read(g.start.month, day)
        return month_tabs[g.start.month]

    listed = {r.number for g, rows, _ in groups if g.accounts is not None for r in rows}
    info = fetch.orders([n for n, _ in paid_rows] + sorted(listed))
    notes = rep_notes.latest(listed, day) if listed else {}

    for g, rows, status in groups:
        fcl = g.mode == "FCL"
        if status is None:
            log.append(f"{g.title} — window not on the Email Schedule; using its orders' dates on the "
                       f"{order_tabs.tab_name(g.start.month)} tab.")
            own = [tab_for(g)[r.number] for r in rows if r.number in tab_for(g)]
            sent = [o.last for o in own if o.last]
            planned = [o.plan for o in own if o.plan]
            if not fcl:
                g.last = max(sent, key=lambda s: s.day).worded(done=True) if sent else None
                g.plan = min(planned, key=lambda s: s.day).worded(done=False) if planned else None
        elif not fcl:
            g.last = status.last.worded(done=True) if status.last else None
            g.plan = status.next.worded(done=False) if status.next else None

        if g.accounts is None:
            continue
        steps = tab_for(g)
        missing = [r.number for r in rows if r.number not in steps]
        if missing:
            log.append(f"{g.title} — not on the {order_tabs.tab_name(g.start.month)} tab: {', '.join(missing)}.")
        names = [(info[r.number].account if r.number in info else "") or r.number for r in rows]
        for r, name in zip(rows, names):
            o = info.get(r.number)
            s = steps.get(r.number)
            # An order with no plan of its own follows its window's schedule.
            plan = s.plan_worded(fcl) if s else None
            if not plan and status and status.next:
                plan = status.next.worded(done=False, fcl=fcl)
            g.accounts.append(text_gen.Account(
                # Two SOs from one account: tell them apart by number.
                name=f"{name} - {r.number}" if names.count(name) > 1 else name,
                rep=rep_short(o.territory) if o else None,
                note=notes.get(r.number),
                last=s.last.worded(done=True, fcl=fcl) if s and s.last else None,
                plan=plan,
            ))
        g.accounts.sort(key=lambda a: a.name.casefold())

    # ---- paid
    paid = []
    for number, ship in paid_rows:
        o = info.get(number)
        if o is None or fetch.mode(o.shipment) is None:
            log.append(f"Paid {number}: AIR/FCL unknown (Estimated Shipment Name {o.shipment if o else 'not found'!r}).")
        paid.append((fetch.mode(o.shipment) if o else None, parse(ship, day) or str(ship)))

    log.append(f"Paid SOs updated today (sheet): {len(paid)}.")
    log.append(f"Unpaid: {len(unpaid)} SOs in {len(groups)} groups "
               f"({sum(g.accounts is not None for g, _, _ in groups)} listed per account).")
    if listed:
        log.append(f"Problem notes found for {len(notes)} of {len(listed)} listed orders.")

    text = text_gen.build(day, settings.dmm_recap_recipient, paid, [g for g, _, _ in groups])
    log.append(f"Recap built ({len(text.splitlines())} lines).")
    return {"recap": text, "log": log}


if __name__ == "__main__":
    import json

    print(json.dumps(run(), indent=2))
