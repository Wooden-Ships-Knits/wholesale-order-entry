import os
import math
import pandas as pd
from dotenv import load_dotenv
from simple_salesforce import Salesforce
import re
from .varia import (
    SHOW_SWATCHES, SHOW_PRICE,
    SW_W, SW_H, HERO_U, SW_U, MAXCOLS, SUB, FINE,
    DPI, UNIT_IN, BLOCK_W, PER_ROW,
    SWATCH_ROW_GAP, SWATCH_COL_GAP,
    BLOCK_COL_GAP, BLOCK_ROW_GAP, MARGIN_L, MARGIN_R, MARGIN_T, MARGIN_B,
    LABEL_WRAP_WIDTH, LABEL_FONTSIZE, LABEL_PAD, TITLE_FONTSIZE, TITLE_PAD_IN,
    OVAL_W_SCALE, OVAL_H_SCALE, OVAL_Y_FACTOR, OVAL_COLOR, OVAL_LW,
    CARD_BG, SWATCH_BORDER, season_code
)
import matplotlib.pyplot as plt
from PIL import Image
from matplotlib import gridspec
from matplotlib.patches import Ellipse 
import textwrap
from pathlib import Path
from app.config import settings
from app.salesforce.client import _client
from app.drive import client as drive



sf = _client()

# --- parse labels out of the filenames ---
def safe_filename(name):
    # name = re.sub(r'[<>:"”“_.|?*]', "", name)  # ot
    name = re.sub(r'[/\\]', "_", name)  # other problematic chars
    name = re.sub(r"\s+", " ", name).strip()
    return name

def style_number(path):
    m = re.search(r'#\s*(\d+)', os.path.basename(path))
    return f"#{m.group(1)}" if m else ""

def color_name(path):
    stem = os.path.splitext(os.path.basename(path))[0]
    stem = stem.replace("_","/")
    return stem.split('-')[-1].strip().upper()   # "Emily Crew Chunky-Kale Green" -> "KALE GREEN"

# NOTE: all card sizing / spacing constants now live in config/varia.py
# (imported above) so they can be tweaked in one place.


def _style_path() -> str:
    """Drive folder holding this season's hero photos."""
    return f"{settings.notice_style_images_dir}/{season_code}"


def _swatch_path() -> str:
    return f"{settings.notice_swatch_images_dir}/{season_code}"


def _open(drive_path: str, filename: str):
    """A photo, streamed from Drive into memory — never written to disk."""
    return Image.open(drive.open_image(drive_path, filename))


def _match_key(name):
    """Normalize a style/filename for matching: lowercase and drop '/' and '_'.
    The two image folders encode a slash differently — style photos write 'L/S'
    as 'LS', swatch photos as 'L_S' — so removing both lets a style match either.
    Apply this to BOTH the style and the filename being compared."""
    return name.replace("/", "").replace("_", "").lower()


def _wrap_label(cname, width=LABEL_WRAP_WIDTH):
    """Wrap a color label without ever cutting a word in half.
    Each '/'-separated part goes on its own line (keeping the trailing '/'),
    then long parts soft-wrap on spaces only (never inside a word)."""
    parts = [p.strip() for p in cname.split("/") if p.strip()]
    lines = []
    for i, part in enumerate(parts):
        if i < len(parts) - 1:      # keep the slash on every part but the last
            part = part + "/"
        lines.append(textwrap.fill(part, width=width, break_long_words=False))
    return "\n".join(lines)


def _draw_style_block(fig, subspec, style, chosen=None, price=None, sw_rows_slots=None):
    """Render one style (hero photo + labeled swatch row) into `subspec`,
    a cell of an outer GridSpec. Draws an oval around each chosen color.

    price comes straight off the sales order line, so it is the price this
    order was actually placed at; a non-numeric price renders as "N/A". It is
    only drawn when SHOW_PRICE is on.

    sw_rows_slots reserves a fixed number of swatch-row slots so the hero photo
    keeps the same size across blocks; extra slots just stay empty below.

    With SHOW_SWATCHES off (config/varia.py) the swatch strip and its ovals are
    skipped entirely and the block is just the hero photo plus its title."""

    # the hero photo is per-color, so a block can only show one of them: with
    # swatches off build_card has already split the styles so `chosen` is a
    # single color, otherwise we fall back to the first one ordered
    chosen_label = chosen[0] if isinstance(chosen, list) else chosen
    color = chosen_label.replace("/", " ")
    # Filenames come from a cached Drive listing (metadata only); the matched
    # photo is downloaded further down, so a card fetches what it draws.
    style_list_path = _style_path()
    style_list = drive.list_images(style_list_path)

    style_any = [f for f in style_list if _match_key(style) in _match_key(f)]
    style_list_filtered = [f for f in style_any if color.lower() in f.lower()]

    # with SHOW_SWATCHES off there is nothing below the hero, so the block
    # reserves no swatch rows and stays a plain photo + title
    swatches, colors, chosen_norm = [], [], set()
    n = sw_cols = slots = 0
    if SHOW_SWATCHES:
        swatch_list_path = _swatch_path()
        swatch_list = drive.list_images(swatch_list_path)
        swatch_list_filtered = [f for f in swatch_list if _match_key(style) in _match_key(f)]

        swatches = sorted(swatch_list_filtered)
        colors   = [color_name(p) for p in swatches]

        if chosen is None:
            chosen_norm = set()
        elif isinstance(chosen, str):
            chosen_norm = {chosen.strip().upper()}
        else:                                    # list/tuple of colors
            chosen_norm = {c.strip().upper() for c in chosen}

        n = max(len(swatches), 1)
        # wrap swatches into a balanced grid: <=4 per row, rows as even as possible
        # 5 -> 3,2 | 6 -> 3,3 | 7 -> 4,3 | 8 -> 4,4 | <=4 -> single row
        sw_rows = math.ceil(n / MAXCOLS)
        sw_cols = math.ceil(n / sw_rows)

        # reserve this many swatch-row slots (>= our own) so the hero keeps a
        # constant size across blocks; any extra rows just stay empty below
        slots = max(sw_rows_slots or sw_rows, sw_rows)

    # nested grid: hero row on top, then swatch row(s) over a fixed FINE-column
    # metric so each swatch is a constant-size slot (centered when a row is short)
    inner = gridspec.GridSpecFromSubplotSpec(
        1 + slots, FINE, subplot_spec=subspec,
        height_ratios=[HERO_U] + [SW_U] * slots,
        hspace=SWATCH_ROW_GAP, wspace=SWATCH_COL_GAP)

    ax_hero = fig.add_subplot(inner[0, :])   # hero spans the full swatch-grid width
    if not style_list_filtered and SHOW_SWATCHES:
        # the block stands for the whole style (the swatches name the colors),
        # so any color's photo is a fair illustration
        style_list_filtered = style_any
    if style_list_filtered:
        ax_hero.imshow(_open(style_list_path, style_list_filtered[0]))
    else:
        # per-color block: another color's photo would sit under this color's
        # name, so leave it empty rather than mislabel it
        print(f"[build_card] no hero photo for style {style!r} / color {color!r}")
    ax_hero.axis("off")

    # swatch strip + the oval marking each chosen color (skipped entirely when
    # SHOW_SWATCHES is off, since `swatches` is empty then)
    first_row_ax = None
    for i, (sw, cname) in enumerate(zip(swatches, colors)):
        r, pos = divmod(i, sw_cols)
        k = min(sw_cols, n - r * sw_cols)        # how many swatches in THIS row
        off = (FINE - k * SUB) // 2              # center the row in the fixed metric
        c0 = off + pos * SUB
        ax = fig.add_subplot(inner[1 + r, c0:c0 + SUB])
        ax.imshow(_open(swatch_list_path, sw).resize((SW_W, SW_H)))
        ax.set_xticks([]); ax.set_yticks([])

        is_chosen = cname in chosen_norm
        if is_chosen:
            # Ellipse(center, width, height): center on the swatch, slightly smaller than it
            ax.add_patch(Ellipse((SW_W / 2, SW_H / OVAL_Y_FACTOR),
                                 width=SW_W * OVAL_W_SCALE, height=SW_H * OVAL_H_SCALE,
                                 fill=False, edgecolor=OVAL_COLOR, lw=OVAL_LW, zorder=5, clip_on=False))
        for s in ax.spines.values():
            s.set_edgecolor(SWATCH_BORDER)

        label = _wrap_label(cname)   # split on "/" and never break a word mid-way
        ax.set_xlabel(label, fontsize=LABEL_FONTSIZE, labelpad=LABEL_PAD)
        if r == 0:
            first_row_ax = ax

    # the number belongs to the style, so read it off any of its photos — a
    # color with no photo of its own still gets its "#347"
    num = style_number(style_any[0]).replace("#", r"\#") if style_any else ""
    hero_pos = ax_hero.get_position()
    if first_row_ax is not None:
        # title text in the gap between this block's hero and the first swatch row
        y_title, va = (hero_pos.y0 + first_row_ax.get_position().y1) / 2, "center"
    else:
        # no swatch row, so no gap below the hero: hang the title just under it
        # (fixed clearance in inches) instead of printing over the photo
        y_title, va = hero_pos.y0 - TITLE_PAD_IN / fig.get_figheight(), "top"
    x_center = (hero_pos.x0 + hero_pos.x1) / 2
    title = rf"$\mathbf{{{num}}}$  {style.upper()}"
    if SHOW_PRICE:
        price_str = f"\\${price:g}" if isinstance(price, (int, float)) and pd.notna(price) else "N/A"
        title += rf"  ${{{price_str}}}$"
    if not SHOW_SWATCHES:
        # no swatch labels to name the color, so spell it out under the style
        title += f"\n{chosen_label.upper()}"
    fig.text(x_center, y_title, title,
             ha="center", va=va, fontsize=TITLE_FONTSIZE, linespacing=1.6)

    # only meaningful while the swatch strip is drawing — chosen_norm is empty
    # when SHOW_SWATCHES is off, so this stays quiet
    missing = chosen_norm - set(colors)
    if missing:
        if not colors:
            print(f"[build_card] {style!r}: NO swatch photos matched this style "
                  f"(cannot place {sorted(missing)}) — check the swatch filenames")
        else:
            print(f"[build_card] {style!r}: chosen {sorted(missing)} not among "
                  f"swatches {colors}")


def _count_swatches(style):
    """How many swatch photos match this style (drives swatch-row wrapping)."""
    return sum(1 for f in drive.list_images(_swatch_path())
               if _match_key(style) in _match_key(f))


def build_card(items, save_to=None, per_row=PER_ROW):
    """Render every style onto one figure, laid out in a balanced grid.

    items   : list of (style, chosen, price) — chosen is a color name or list
              of names, price is the sales-order line price for that style.
    per_row : max style blocks per row. The grid stays balanced and only wraps
              past this many: 4->[4], 5->[5], 6->[3,3], 7->[4,3], 8->[4,4], ...

    With SHOW_SWATCHES on, one block per style covers every color via its
    swatch strip. With it off there is no swatch strip, so each ordered color
    gets its own block showing that color's hero photo.
    """
    items = list(items)
    if not SHOW_SWATCHES:
        # split each style into one block per ordered color, keeping the order
        # the colors came off the sales order
        items = [(style, c, price)
                 for style, chosen, price in items
                 for c in (chosen if isinstance(chosen, list) else [chosen])]
    n_styles = max(len(items), 1)
    # balanced outer grid: as few rows as possible, then even columns
    nrows = math.ceil(n_styles / per_row)
    ncols = math.ceil(n_styles / nrows)

    if SHOW_SWATCHES:
        # swatch-row count per style, and the tallest block in each outer row — a
        # row's height grows with its swatches while the hero photo stays fixed
        sw_rows_per = [max(math.ceil(max(_count_swatches(style), 1) / MAXCOLS), 1)
                       for style, _, _ in items]
        row_slots = [max(sw_rows_per[r * ncols:(r + 1) * ncols] or [1])
                     for r in range(nrows)]
        row_heights = [HERO_U + SW_U * m for m in row_slots]
    else:
        # hero photos only: no swatch rows, so every block is just the photo
        row_slots = [0] * nrows
        row_heights = [HERO_U] * nrows

    fig = plt.figure(figsize=(BLOCK_W * ncols, sum(row_heights) * UNIT_IN), dpi=DPI)
    fig.patch.set_facecolor(CARD_BG)
    outer = gridspec.GridSpec(nrows, ncols, figure=fig, height_ratios=row_heights,
                              left=MARGIN_L, right=MARGIN_R, top=MARGIN_T, bottom=MARGIN_B,
                              wspace=BLOCK_COL_GAP, hspace=BLOCK_ROW_GAP)

    for idx, (style, chosen, price) in enumerate(items):
        r, c = divmod(idx, ncols)
        _draw_style_block(fig, outer[r, c], style, chosen, price=price,
                          sw_rows_slots=row_slots[r])

    if save_to:
        fig.savefig(save_to, facecolor=CARD_BG, bbox_inches="tight")
        print("saved", save_to)
        plt.show()
    return fig


def item_fetch(SO_number=None):
    if SO_number==None:
        return 
    q = f"""
    SELECT Id, Name,
        (SELECT Name,
                kugo2p__ProductName__c,
                Product_Code__c,
                kugo2p__LineDescription__c,
                kugo2p__Quantity__c,
                kugo2p__SalesPrice__c,
                kugo2p__DiscountSalesPrice__c,
                kugo2p__TotalAmount__c,
                kugo2p__Status__c
            FROM kugo2p__Sales_Order_Product_Lines__r
            ORDER BY kugo2p__SortOrder__c)
    FROM kugo2p__SalesOrder__c
    WHERE Name = '{SO_number}'
    """

    order = sf.query(q)["records"][0]
    lines = order["kugo2p__Sales_Order_Product_Lines__r"]["records"]

    lines_df = pd.DataFrame(lines).drop(columns="attributes")
    lines_df['kugo2p__ProductName__c'] = (
        lines_df['kugo2p__ProductName__c'].str.rsplit('-', n=1).str[0]
    )
    lines_df = lines_df.drop_duplicates(subset='kugo2p__ProductName__c')
    df = lines_df[['Name']].copy()
    df['Style'] = lines_df['kugo2p__ProductName__c'].str.rsplit('-', n=1).str[0]
    df['Color'] = lines_df['kugo2p__ProductName__c'].str.rsplit('-', n=1).str[1]
    df['Price'] = lines_df['kugo2p__SalesPrice__c']

    # every line of a style carries the same SalesPrice, so 'first' picks the
    # style's price (and skips nulls if one ever shows up)
    grouped = (
    df.groupby('Style', sort=False)
      .agg(Color=('Color', lambda s: list(dict.fromkeys(s))),
           Price=('Price', 'first'))
      .reset_index()
    )
    styles = grouped['Style'].tolist()
    colors = grouped['Color'].tolist()
    prices = grouped['Price'].tolist()
    items = list(zip(styles, colors, prices))
    out_dir = Path(settings.notice_output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    build_card(items, save_to=str(out_dir / f"{safe_filename(SO_number)} card.png"))
    return grouped
