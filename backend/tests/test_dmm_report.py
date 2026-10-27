"""DMM (Daily Morning Meeting) recap — sheet parsing and the recap layout."""
from datetime import date

from app.reports.daily_morning_meeting import email_schedule as es
from app.reports.daily_morning_meeting import order_tabs, rep_notes, text_gen
from app.reports.daily_morning_meeting.fetch import mode, window_end
from app.reports.daily_morning_meeting.recap import lists_accounts, rep_short
from app.reports.daily_morning_meeting.steps import Step, nearest, parse, step_name

TODAY = date(2026, 10, 26)


# ------------------------------------------------------------- dates
def test_sheet_dates_in_every_spelling():
    assert parse("26-Oct", TODAY) == date(2026, 10, 26)
    assert parse("Send on 10/28", TODAY) == date(2026, 10, 28)
    assert parse("Wed, Oct 28 ", TODAY) == date(2026, 10, 28)
    assert parse("-", TODAY) is None and parse("", TODAY) is None


def test_year_is_the_one_closest_to_today():
    assert nearest(12, 28, date(2027, 1, 5)) == date(2026, 12, 28)
    assert nearest(1, 3, date(2026, 12, 30)) == date(2027, 1, 3)


def test_window_end_is_the_last_day_of_next_month():
    assert window_end(date(2026, 10, 27)) == date(2026, 11, 30)
    assert window_end(date(2026, 11, 2)) == date(2026, 12, 31)
    assert window_end(date(2026, 12, 15)) == date(2027, 1, 31)


# ------------------------------------------------------------- step names
def test_step_names_from_both_sheets():
    assert step_name("EMAIL  #1") == "email #1"
    assert step_name("email 5") == "email #5"
    assert step_name("Reply to All - to follow up for email #2") == "follow-up email #2"  # not "to rep"
    assert step_name("Follup Email #2") == "follow-up email #2"
    assert step_name("Reply to All - 2nd follow up for email #5") == "2nd follow-up email #5"
    assert step_name("FOLLOW UP EMAIL #7\nTo Rep & Cust") == "follow-up email #7 to rep & cust"
    assert step_name("Follup Email #7 (Rep & cust)") == "follow-up email #7 to rep & cust"
    assert step_name("EMAIL CC NOTIFICATION") == "CC notification email"
    for other in ("CHARGING THE ORDER", "PLAN CXL DATE", "Email PL to Rep", "SHIP WINDOW", "Note"):
        assert step_name(other) is None


def test_fcl_steps_are_notices():
    s = Step(date(2026, 10, 26), "email #4")
    assert s.worded(done=True, fcl=True) == "Mon, Oct 26 - Sent notice #4"
    assert s.worded(done=False) == "Mon, Oct 26 - Send email #4"


def test_mode_from_shipment_name():
    assert mode("06-05 FCL") == "FCL" and mode("10-01 AIR") == "AIR"
    assert mode("-") is None and mode("") is None


def test_accounts_listed_only_up_to_three_sos():
    ended = es.Status(last=None, next=None, ended=True)
    running = es.Status(last=None, next=None, ended=False)
    assert lists_accounts("FCL", running, 3) and lists_accounts("AIR", ended, 2)
    assert not lists_accounts("FCL", running, 4)  # e.g. November FCL, 16 SOs: group line + Plan
    assert not lists_accounts("AIR", ended, 4)
    assert not lists_accounts("AIR", running, 1) and not lists_accounts("AIR", None, 1)


def test_rep_short():
    assert rep_short("FL - Jason Hilsenrad") == "Jason"
    assert rep_short("NM/MT - House") == "House"
    assert rep_short("AK / AZ / NE / NV") == "House"
    assert rep_short("") is None


# ------------------------------------------------------------- Email Schedule
def _serial(d: date) -> int:
    return (d - date(1899, 12, 30)).days


SCHEDULE_HEADER = ["", "SHIP WINDOW", "EMAIL CC NOTIFICATION", "EMAIL  #1",
                   "Reply to All - to follow up for email #1", "EMAIL  #2", "EMAIL #8", "PLAN CXL DATE"]


def _schedule(*rows) -> es.Schedule:
    values = [[], [], [], [], SCHEDULE_HEADER, [], ["Email Distribution", "From: wholesale"]]
    values += [list(r) for r in rows]
    return es.Schedule(values, TODAY)


def test_schedule_last_and_next_step():
    s = _schedule(
        ["NOVEMBER", "11/1 - 11/20", _serial(date(2026, 10, 19)), _serial(date(2026, 10, 21)),
         _serial(date(2026, 10, 26)), _serial(date(2026, 10, 29)), "N/A", _serial(date(2026, 12, 1))],
    )
    st = s.status("11/01 - 11/20")  # zero-padded in Salesforce, not in the sheet
    assert st.last == Step(date(2026, 10, 26), "follow-up email #1")
    assert st.next == Step(date(2026, 10, 29), "email #2")
    assert not st.ended
    assert s.status("12/01 - 12/20") is None


def test_schedule_ended_after_the_last_email():
    s = _schedule(["OCT", "10/1 - 10/20", _serial(date(2026, 9, 21)), _serial(date(2026, 9, 23)), "N/A",
                   _serial(date(2026, 9, 28)), _serial(date(2026, 10, 26)), _serial(date(2026, 10, 27))])
    st = s.status("10/01 - 10/20")
    assert st.ended and st.next is None
    assert st.last.name == "email #8"


def test_schedule_uses_this_years_row_and_the_updated_plan():
    s = _schedule(
        # last year's row for the same window
        ["OCT", "10/1 - 10/20", _serial(date(2025, 9, 15)), _serial(date(2025, 9, 18)), "", "", "", ""],
        # this year: initial plan, then the updated one below it
        ["OCT", "10/1 - 10/20", _serial(date(2026, 9, 21)), _serial(date(2026, 9, 23)), "", "", "", ""],
        ["", "10/1 - 10/20\nUPDATED", _serial(date(2026, 9, 21)), _serial(date(2026, 9, 24)), "", "", "", ""],
    )
    assert s.status("10/01 - 10/20").last == Step(date(2026, 9, 24), "email #1")


# ------------------------------------------------------------- month tab
MONTH_HEADER = ["Order: Order Number", "Account Name", "AIR/FCL?", "email CC notif", "email 1", "email 2",
                "Follup Email #2", "email 3", "Email PL to Rep", "email 4", "CXL Date"]


def test_month_tab_last_sent_and_next_plan():
    values = [["Added to Problem List"], MONTH_HEADER,
              ["SO-1", "FOXGLOVE", "FCL", "-", "23-Sep", "28-Sep", "-", "24-Oct", "26-Oct", "Send on 10/28", ""],
              ["SO-2", "SUGAR", "FCL", "-", "21-Oct", "Send after oct order deliv.", "", "", "", "", ""],
              ["SO-3", "EVO SPA", "FCL", "-", "21-Oct", "Charge on 11/11", "", "", "", "", ""],
              ["Total", "", "", "", "", "", "", "", "", "", ""]]
    tab = order_tabs.parse_tab(values, TODAY)
    assert set(tab) == {"SO-1", "SO-2", "SO-3"}
    # 'Email PL to Rep' (26-Oct) is not a customer email
    assert tab["SO-1"].last == Step(date(2026, 10, 24), "email #3")
    assert tab["SO-1"].plan_worded(fcl=True) == "Wed, Oct 28 - Send notice #4"
    assert tab["SO-2"].plan_worded(fcl=True) == "Send after oct order deliv."
    assert tab["SO-3"].plan_worded(fcl=True) == "Wed, Nov 11 - Charge the order"


def test_month_tab_names():
    assert order_tabs.tab_name(10) == "OCT" and order_tabs.tab_name(11) == "NOV"


# ------------------------------------------------------------- rep notes
def test_latest_dated_note_only():
    values = [["HARBOUR THREAD", "F26 SWEATERS 10/01 - 10/20", "$1,201",
               "10/14 - The rep will certainly contact the cust.\n10/21 - The rep has reached out to the cust.",
               "SO-1"],
              ["OTHER", "F26 SWEATERS 10/01 - 10/20", "10/22 - Not ours.", "SO-9"]]
    notes = sorted(rep_notes.notes_in(values, {"SO-1"}, TODAY), key=lambda n: n[1])
    # the ship window '10/01 - 10/20' is not a note
    assert [(n, d.day, t) for n, d, t in notes] == [
        ("SO-1", 14, "The rep will certainly contact the cust."),
        ("SO-1", 21, "The rep has reached out to the cust."),
    ]


# ------------------------------------------------------------- layout
def test_paid_lines_air_first_with_plurals():
    text = text_gen.build(TODAY, "Paola", [
        ("FCL", date(2026, 10, 27)),
        ("AIR", date(2026, 10, 28)), ("AIR", date(2026, 10, 28)), ("AIR", date(2026, 10, 28)),
    ], [])
    assert "Today, we have a total of 4 orders that have been paid.\n" \
           "- For 3 AIR SOs, we plan to ship them on Wed, Oct 28 (LT = 2 days) at the latest.\n" \
           "- For 1 FCL SO, we plan to ship it on Tue, Oct 27 (LT = 1 day) at the latest." in text
    assert "Daily Morning Meeting Update - Monday, October 26, 2026." in text


def test_group_and_per_account_layout():
    oct_air = text_gen.Group("F26", "AIR", "10/01 - 10/30", date(2026, 10, 1), 24, 733, 49080.4,
                             last="Mon, Oct 26 - Sent email #6", plan="Fri, Oct 30 - Send email #7")
    oct_fcl = text_gen.Group("F26", "FCL", "10/01 - 10/30", date(2026, 10, 1), 1, 45, 3090, accounts=[
        text_gen.Account("WILDFLOWER WOMEN", "Rande", "Wed, Oct 14 - The cust will take the order later.",
                         "Mon, Oct 26 - Sent notice #5", "Wed, Oct 28 - Send notice #6")])
    nov = text_gen.Group("F26", "AIR", "11/01 - 11/20", date(2026, 11, 1), 44, 1235, 84152)
    text = text_gen.build(TODAY, "Paola", [], [nov, oct_fcl, oct_air])
    assert "Today, we have no orders that have been paid." in text
    # October before November, AIR before FCL
    assert text.index("October AIR") < text.index("October FCL") < text.index("November AIR")
    assert ("*UNPAID F26 October AIR (10/01 - 10/30) order:*\n"
            "- # of SO: 24 SO, TTL Qty: 733, TTL Amount: $49,080\n"
            "- Last communication: Mon, Oct 26 - Sent email #6.\n"
            "- Plan: Fri, Oct 30 - Send email #7.") in text
    assert ("- Details as below:\n"
            "1. WILDFLOWER WOMEN (Rande)\n"
            "- Wed, Oct 14 - The cust will take the order later.\n"
            "- Mon, Oct 26 - Sent notice #5.\n"
            "- PLAN: Wed, Oct 28 - Send notice #6.") in text
    assert "TTL Qty: 1,235, TTL Amount: $84,152\n- Plan: (none scheduled)" in text
    assert text.endswith("Thanks!")
