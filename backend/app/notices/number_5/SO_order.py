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
    CARD_BG, SWATCH_BORDER, HERO_TRIM_TOL, season_code
)
import matplotlib.pyplot as plt
from PIL import Image, ImageChops
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


def _hero_choice(style, chosen):
    """(hero photo filename or None, every photo of the style) for one block.

    The hero photo is per-color, so a block can only show one of them: with
    swatches off build_card has already split the styles so `chosen` is a
    single color, otherwise we fall back to the first one ordered."""
    chosen_label = chosen[0] if isinstance(chosen, list) else chosen
    color = chosen_label.replace("/", " ")
    # Filenames come from a cached Drive listing (metadata only); only the
    # photo picked here is downloaded.
    style_any = [f for f in drive.list_images(_style_path()) if _match_key(style) in _match_key(f)]
    picked = [f for f in style_any if color.lower() in f.lower()]
    if not picked and SHOW_SWATCHES:
        # the block stands for the whole style (the swatches name the colors),
        # so any color's photo is a fair illustration
        picked = style_any
    if not picked:
        # per-color block: another color's photo would sit under this color's
        # name, so leave it empty rather than mislabel it
        print(f"[build_card] no hero photo for style {style!r} / color {color!r}")
    return (picked[0] if picked else None), style_any


def _prep_hero(img, height_px):
    """The hero photo ready to draw: on white, its white left/right margins
    trimmed, and scaled down to the height it prints at.

    Only the SIDES are trimmed: they are what makes a front + back photo look
    wider than its garments. Top and bottom keep the studio's framing, which is
    what keeps a cropped tank shorter than a long cardigan on the card.
    Scaling down to print size also keeps memory low — the originals are far
    larger than the card needs. It happens first (trimming the sides doesn't
    change the height), and a JPEG is decoded straight at the smaller size, so
    the full-size original is never held in memory."""
    if img.format == "JPEG" and img.height > height_px:
        img.draft("RGB", (img.width * height_px // img.height, height_px))
    if img.height > height_px:
        img = img.resize((max(round(img.width * height_px / img.height), 1), height_px), Image.LANCZOS)
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        flat = Image.new("RGB", img.size, CARD_BG)
        flat.paste(img, mask=img.getchannel("A"))
        img = flat
    else:
        img = img.convert("RGB")
    ink = ImageChops.difference(img, Image.new("RGB", img.size, CARD_BG)).convert("L")
    box = ink.point(lambda p: 255 if p > HERO_TRIM_TOL else 0).getbbox()
    if box:
        pad = max(img.width // 100, 2)
        img = img.crop((max(box[0] - pad, 0), 0, min(box[2] + pad, img.width), img.height))
    return img


def _split_rows(units, per_row):
    """Blocks (in order) split into rows: as few rows as keep each within
    per_row units of width, then as even as possible — the top rows taking the
    extra on a tie, so 5 -> [5], 6 -> [3, 3], 7 -> [4, 3] for plain blocks. A
    block twice as wide counts as about 2."""
    n = len(units)
    if n == 0:
        return []
    pre = [0.0]
    for u in units:
        pre.append(pre[-1] + u)

    def partition(k):
        memo = {}

        def best(i, k):  # rows for blocks i.. in k rows -> (widest row, cut points)
            if k == 1:
                return pre[n] - pre[i], (n,)
            if (i, k) not in memo:
                res = None
                for j in range(i + 1, n - k + 2):
                    widest, cuts = best(j, k - 1)
                    cand = (max(pre[j] - pre[i], widest), (j,) + cuts)
                    if res is None or cand[0] <= res[0] + 1e-9:
                        res = cand
                memo[(i, k)] = res
            return memo[(i, k)]

        return best(0, k)

    k = max(math.ceil(pre[n] / per_row - 1e-9), 1)
    while True:
        widest, cuts = partition(k)
        if widest <= per_row + 1e-9 or k >= n:
            break
        k += 1
    rows, start = [], 0
    for c in cuts:
        rows.append(list(range(start, c)))
        start = c
    return rows


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


def _draw_style_block(fig, subspec, style, chosen=None, price=None, sw_rows_slots=None,
                      hero=None, style_any=()):
    """Render one style (hero photo + labeled swatch row) into `subspec`,
    this block's place on the card. Draws an oval around each chosen color.

    hero is the photo already prepared by build_card (_prep_hero), or None;
    style_any every photo filename of the style (for its "#347" number).

    price comes straight off the sales order line, so it is the price this
    order was actually placed at; a non-numeric price renders as "N/A". It is
    only drawn when SHOW_PRICE is on.

    sw_rows_slots reserves a fixed number of swatch-row slots so the hero photo
    keeps the same size across blocks; extra slots just stay empty below.

    With SHOW_SWATCHES off (config/varia.py) the swatch strip and its ovals are
    skipped entirely and the block is just the hero photo plus its title."""

    chosen_label = chosen[0] if isinstance(chosen, list) else chosen

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
    if hero is not None:
        ax_hero.imshow(hero)
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
              A block widened for a wide photo counts as its width (~2 for a
              front + back photo).

    Every hero photo is drawn at the SAME height, and each block is as wide as
    its photo needs at that height (never narrower than a plain block). So a
    front + back photo gets a block about twice as wide, and its garments come
    out the size of the single ones beside it.

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

    # Sizes in inches. These reproduce the old fixed grid for plain photos:
    # the hero height and block width a one-row card used to get.
    hero_h = HERO_U * UNIT_IN * (MARGIN_T - MARGIN_B)
    plain_w = BLOCK_W * (MARGIN_R - MARGIN_L) / (1 + BLOCK_COL_GAP)
    col_gap = BLOCK_COL_GAP * plain_w
    row_gap = BLOCK_ROW_GAP * hero_h
    pad, title_room = 0.3, 0.8  # page edge, and room for the last row's titles

    # The photos come first: their shapes decide the layout.
    heroes, anys = [], []
    for style, chosen, _ in items:
        name, style_any = _hero_choice(style, chosen)
        heroes.append(_prep_hero(_open(_style_path(), name), round(hero_h * DPI)) if name else None)
        anys.append(style_any)
    widths = [max(plain_w, h.width / h.height * hero_h) if h else plain_w for h in heroes]
    rows = _split_rows([w / plain_w for w in widths], per_row)

    if SHOW_SWATCHES:
        # swatch-row count per style, and the tallest block in each row — a
        # row's height grows with its swatches while the hero photo stays fixed
        sw_rows_per = [max(math.ceil(max(_count_swatches(style), 1) / MAXCOLS), 1)
                       for style, _, _ in items]
        row_slots = [max(sw_rows_per[i] for i in row) for row in rows]
    else:
        # hero photos only: no swatch rows, so every block is just the photo
        row_slots = [0] * len(rows)
    row_h = [hero_h * (HERO_U + SW_U * m) / HERO_U for m in row_slots]

    content_w = max([sum(widths[i] for i in row) + col_gap * (len(row) - 1) for row in rows] or [plain_w])
    fig_w = content_w + 2 * pad
    fig_h = sum(row_h) + row_gap * max(len(rows) - 1, 0) + 2 * pad + title_room
    fig = plt.figure(figsize=(fig_w, fig_h), dpi=DPI)
    fig.patch.set_facecolor(CARD_BG)

    # Rows top to bottom, blocks left to right, each at its own width; a row
    # narrower than the widest is centered, so it leaves no hole on one side.
    top = fig_h - pad
    for r, row in enumerate(rows):
        x = pad + (content_w - sum(widths[i] for i in row) - col_gap * (len(row) - 1)) / 2
        for i in row:
            style, chosen, price = items[i]
            spec = gridspec.GridSpec(1, 1, figure=fig,
                                     left=x / fig_w, right=(x + widths[i]) / fig_w,
                                     top=top / fig_h, bottom=(top - row_h[r]) / fig_h)[0]
            _draw_style_block(fig, spec, style, chosen, price=price, sw_rows_slots=row_slots[r],
                              hero=heroes[i], style_any=anys[i])
            x += widths[i] + col_gap
        top -= row_h[r] + row_gap

    if save_to:
        fig.savefig(save_to, facecolor=CARD_BG, bbox_inches="tight")
        print("saved", save_to)
        # Not plt.show(): on the server it draws nothing. Close instead — pyplot
        # keeps every open figure (and its photos) in memory until closed, so
        # each card generated would otherwise stay in the backend's RAM.
        plt.close(fig)
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
