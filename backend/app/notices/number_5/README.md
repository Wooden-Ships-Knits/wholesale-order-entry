# Swatch Cropper & Collection Tools

A small workspace of Python scripts and Jupyter notebooks for processing seasonal
product imagery and collection data. Two main jobs:

1. **Swatch cropping / OCR** — detect and crop individual color **swatches** out of
   hanging-swatch photos, read their `Style-Color` labels with a vision LLM, and file
   the crops under `thumbnails/swatch/` and `thumbnails/swatch-color/`.
2. **Order → product cards** — pull each sales order's line items from Salesforce
   (SOQL) and render a catalog-style **product card**: one block per style (hero photo
   + optional labeled swatch grid), with the ordered colors circled.

## Contents

| File | Purpose |
| --- | --- |
| `main.py` | Entry point. Loops over `SO_list` from `config/varia.py`, clears old `temporary/*card.png`, and runs `SO_order.item_fetch()` per SO — one card file per order, with a pass/fail tally at the end. |
| `SO_order.py` | Builds **one combined card** per order — all styles laid out in a balanced grid, uniform swatch sizes, ordered colors circled. The current/primary card builder. |
| `SO_order_single_shot.py` | Older variant: builds **one PNG per style** (a separate card file for each). Kept for reference / one-off cards. Still uses `setup.py` + the IM MASTER spreadsheet for pricing. |
| `swatch_cropper.py` | The swatch pipeline as a runnable script: walk `hanging_swatch/<season>/`, crop each swatch, OCR its label, rename, then do the second (color-only) crop. |
| `swatch_cropper.ipynb` | Same pipeline as a notebook, plus **manual re-run cells** (`##UNTUK RUNNING TERPISAH`) for redoing just the crop or just the OCR on one sheet. |
| `card_generator.ipynb` | Interactive notebook where `build_card()` was prototyped — hero photo + labeled swatch row with an oval around the chosen color(s). |
| `explore.ipynb` | Scratchpad for Salesforce/SOQL work — running the Kugamon subquery against one SO and poking at the resulting DataFrame. |
| `setup.py` | Shared Google Sheets / Drive auth (`gspread` + service account) and cached readers for sheets and Excel files. Only `SO_order_single_shot.py` uses it now. |
| `config/varia.py` | All tweakable constants kept out of the code: `season` / `SO_list`, the IM-sheet settings (`IM_header`, `WHL`), the `SHOW_SWATCHES` / `SHOW_PRICE` toggles, **and the entire card layout** — output scale (`DPI`, `UNIT_IN`, `BLOCK_W`, `PER_ROW`), hero-vs-swatch heights (`HERO_U`, `SW_U`), the swatch grid (`MAXCOLS`, `SUB`, `FINE`, `SW_W`, `SW_H`), spacing, page margins, label text, the chosen-color oval, and figure colors. Tweak sizing here — not in `SO_order.py`. |
| `config/launcher_params.json` | Written by the Report Launcher dashboard to override `season` and `SO_list`. Optional — see [Running a batch](#running-a-batch). |
| `requirements.txt` | Pinned dependency set for the `venv/` in this folder. |

> **Notebooks are git-ignored.** `.gitignore` now excludes `*.ipynb` (along with
> `thumbnails/`, `hanging_swatch/`, `temporary/`, `credentials/`, `*.json`, `*.xlsx`,
> `venv/`), so the notebooks above live only on this Drive copy and won't show up in
> `git status`.

## Directory layout

```
hanging_swatch/<season>/<collection>/   Input photos for swatch_cropper (e.g. "27 SPRING/")
  hide/                                 Park folders here to keep them out of the loop
cropped_swatches/    Stage-1 crops, before OCR renaming        (git-ignored)
thumbnails/
  swatch/<code>/          Stage-1 crops renamed to "Style-Color.jpeg"
  swatch-color/<code>/    Stage-2 color-only tiles — what the cards use  (e.g. S27/)
  example/, style/        Older sample / local style-photo folders
temporary/           Generated product-card PNGs               (git-ignored)
credentials/         Service-account JSON keys                 (git-ignored)
config/              Constants (varia.py) + launcher_params.json
venv/                Local virtualenv                          (git-ignored)
```

Note: `SO_order.py` reads **both** the hero/style photos and the swatch tiles from
external Drive paths, not from the local `thumbnails/`:

- hero photos — `PTIF SERVER/PPIC/CC OC Salesforce/LIBRARY MODEL IMAGE/<code>`
- swatch tiles — `PTIF SERVER/PPIC/AUTOMATION/Payment Notice 5/Payment Notice 5/thumbnails/swatch-color/<code>`

Both are hard-coded near the top of `_draw_style_block()`, each with the local
`thumbnails/...` equivalent commented out just above it — swap the comment to run
against local folders.

## Setup

Requires Python 3.11 (the checked-in `venv/` is 3.11.9). Install from the pinned set:

```bash
./venv/bin/python3 -m pip install -r requirements.txt
```

### Environment variables

Create a `.env` file in this folder (it is git-ignored — never commit it). The
scripts load it with `load_dotenv()`, so `.env` must sit in the directory the
script/notebook runs from (this one).

```
# Salesforce (for SO_order.py / main.py / explore.ipynb)
SALESFORCE_USERNAME=you@example.com
SALESFORCE_PASSWORD=...
SALESFORCE_SECURITY_TOKEN=...

# OpenAI — required by swatch_cropper for the label OCR
OPENAI_API_KEY=sk-...
```

`OPENAI_API_KEY` is **not** currently in `.env`; `swatch_cropper` reads it from the
process environment, so either add it to `.env` or export it before running. The
`CREDS_PATH` entry in `.env` is a leftover — nothing reads it (see below).

### Credentials

`setup.py` authenticates to Google Sheets/Drive with a service-account key whose path
is **hard-coded** at the top of the file (`credentials/dialy-report-automation-*.json`)
— change it there, not via an env var. The whole `credentials/` folder and all `*.json`
files are git-ignored.

## Order → product cards (`main.py` / `SO_order.py`)

### Running a batch

Put the SO numbers in `SO_list` in `config/varia.py`, set `season`, then:

```bash
./venv/bin/python3 main.py
```

`main.py` deletes every existing `temporary/*card.png` first, so the output folder
only ever holds the current run. Each SO is wrapped in its own `try` — one bad order
prints `FAILED: <error>` and the rest still run.

If `config/launcher_params.json` exists, `varia.py` reads `season` and `SO_list` from
it and **overrides** the hand-edited values (an empty `SO_list` in the file is
ignored, so a blank dashboard form won't wipe your defaults). Delete the file to go
back to editing `varia.py` by hand.

### What `item_fetch()` does

1. Connect to Salesforce with `simple_salesforce` (domain `wooden-ships.my`).
2. Run a SOQL query against the Kugamon managed package: the order lives on
   `kugo2p__SalesOrder__c` (looked up by its `Name`, e.g. `SO-260210-0072369`) and the
   items are its `kugo2p__Sales_Order_Product_Lines__r` child records.
3. The product name (e.g. `MERRY EVERYTHING CREW CHUNKY-PURE SNOW-X/S`) is split on
   the **last** `-` to drop the size, deduplicated, then split again to separate
   **Style** from **Color** — so each style maps to its list of ordered colors.
4. Price comes from the line's `kugo2p__SalesPrice__c` (`'first'` per style, since
   every line of a style carries the same price) — i.e. the price the order was
   actually placed at, not a list price.
5. `build_card(items, save_to=...)` renders **all** styles onto one figure and saves a
   single PNG to `temporary/<SO number> card.png`.

> **Salesforce object naming gotchas:** the sObject is `kugo2p__SalesOrder__c`
> (singular, namespaced) — not `Order`/`Orders` (the standard Order object isn't
> enabled in this org). In a parent-to-child subquery you use the **relationship**
> name (`kugo2p__Sales_Order_Product_Lines__r`), not the object name.

### Display toggles (`config/varia.py`)

Two switches change the shape of the card, and they interact:

| Constant | Default | Effect |
| --- | --- | --- |
| `SHOW_SWATCHES` | `False` | `True` → one block per **style**, with its swatch strip and the ovals around ordered colors. `False` → no swatch strip, so `build_card` splits each style into one block per **ordered color**, and the color name is printed under the style title instead. |
| `SHOW_PRICE` | `False` | `True` → the title reads `#347  STYLE NAME  $68`; `False` → price is hidden. A non-numeric price renders as `N/A`. |

With swatches **off**, a block shows that one color's own hero photo, and a color with
no matching photo is left blank rather than mislabeled with another color's picture.
With swatches **on**, the block stands for the whole style, so any of its photos is a
fair illustration and `_draw_style_block` falls back to the first match.

### Card layout (`build_card` / `_draw_style_block`)

> All the sizing/spacing/color constants named below live in `config/varia.py`
> (commented, in Indonesian) and are imported by `SO_order.py`. Adjust the look of
> the card there in one place — no need to touch `SO_order.py`.

- **Balanced outer grid** — up to `per_row=PER_ROW` (5) blocks per row, wrapping
  evenly: 4→`[4]`, 5→`[5]`, 6→`[3,3]`, 7→`[4,3]`, 8→`[4,4]`, …
- **Constant hero size** — each outer row's height grows with its tallest block, and
  blocks are padded to a shared swatch-row count, so the hero photo is the same size
  everywhere (`HERO_U`, `SW_U`, `UNIT_IN` set the scale; lower `SW_U` = smaller swatches).
- **Swatch wrapping** — swatches wrap into a balanced grid, ≤`MAXCOLS` (4) per row
  (5→`3,2`, etc.).
- **Uniform swatch size** — every swatch occupies a fixed slot (`1/MAXCOLS` of the
  block width, centered) so swatches look the same across all blocks (`MAXCOLS`, `SUB`).
- **Labels** never break a word mid-way (`_wrap_label`): each `/`-separated part goes
  on its own line, keeping the trailing `/` (`LABEL_WRAP_WIDTH`, `LABEL_FONTSIZE`,
  `LABEL_PAD`).
- **Title** — `#700 STYLE NAME` in bold, sized by `TITLE_FONTSIZE`. With swatches on
  it sits in the gap between the hero and the first swatch row; with swatches off
  there is no gap, so it hangs `TITLE_PAD_IN` inches below the photo.
- **Chosen colors** matching a swatch are circled with an oval (`OVAL_*` constants).
- **Spacing & colors** — gaps inside a block (`SWATCH_ROW_GAP`, `SWATCH_COL_GAP`),
  between blocks (`BLOCK_COL_GAP`, `BLOCK_ROW_GAP`), page margins (`MARGIN_*`), and
  the figure/border colors (`CARD_BG`, `SWATCH_BORDER`).

> **`_count_swatches()` still reads the local path.** It counts swatch files under
> `thumbnails/swatch-color/<code>/` to size the swatch rows, while
> `_draw_style_block()` loads the images from the Drive path above. With
> `SHOW_SWATCHES = False` it's never called, but if you turn swatches on you need the
> local folder populated too — or point both at the same place.

### Filename-matching gotchas

Styles/colors from Salesforce are matched to image filenames by substring, which runs
into a few naming inconsistencies (`_match_key` normalizes around them — it lowercases
and strips `/` and `_` from **both** the style and the filename):

- A slash in a name is written **differently per folder**: style photos write `L/S`
  as `LS`; swatch photos write it as `L_S`. Stripping both makes them match.
- Color suffixes use the yarn term `Marl` (e.g. `...Royal Coast Marl`); a file spelled
  `Marled` in the *color* part won't match SF's `MARL` (rename the file to `Marl`).
- `[build_card] no hero photo for style X / color Y` means no style photo matched —
  check the filename in LIBRARY MODEL IMAGE.
- `NO swatch photos matched this style` means the style itself didn't match any swatch
  filename; `chosen [...] not among swatches [...]` means the style matched but that
  one color name is spelled differently in SF than in the file.

## Swatch cropping pipeline (`swatch_cropper.py` / `.ipynb`)

Set `season` and `season_code` at the top of the file (e.g. `"27 SPRING"` / `"S27"`),
then run. It walks **every** subfolder of `hanging_swatch/<season>/` — move anything
you want skipped into `hanging_swatch/<season>/hide/`.

**Stage 1 — crop + OCR + rename**, per source photo:

1. Read the sheet with OpenCV and threshold out the white background (`gray < 250`).
2. Morphological close + dilate (10×10 rect kernel) so each swatch becomes one blob.
3. Find external contours, drop boxes smaller than 0.5% of the image, keep the largest
   20, then sort top-to-bottom (banded by `y // 200`) and left-to-right.
4. Show a numbered preview of the detected boxes.
5. Crop each box with 30px padding → `cropped_swatches/swatch_NN.jpeg`.
6. OCR each crop to read its `Style-Color` label, sanitize it (`safe_filename`), and
   **move** the file to `thumbnails/swatch/<code>/<Style-Color>.jpeg`.

**Stage 2 — color-only crop:** re-read everything in `thumbnails/swatch/<code>/` and
crop to the fabric area only (vertical 26%–90%, horizontal 15%–85%), writing to
`thumbnails/swatch-color/<code>/` under the same filename. These tiles are what the
product cards display.

Because stage 1 renames files out of `cropped_swatches/` it is not idempotent — a
re-run OCRs whatever crops are sitting there. The notebook's `##UNTUK RUNNING
TERPISAH` cells exist for exactly this: they re-do just the cropping or just the OCR
for the sheet currently in memory (`boxes`, `img`, `W`, `H`).

### OCR / vision model

Label OCR goes through the OpenAI Responses API:

```python
VISION_MODEL = "o4-mini"
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
```

- The prompt asks for the **underlined** text only, ignoring price and yarn
  composition, and returns `Style-Color` (e.g. `Beach Top Cotton-Darkest
  Indigo/Breaker White`).
- Local files are sent as base64 data URIs (`file_to_data_uri()`) with
  `detail: "high"` — the labels are small, so standard detail loses characters.
- `safe_filename()` strips `<>:"”“_|?*` and turns `/` into `_`, which is why swatch
  filenames encode `L/S` as `L_S` (see the matching gotchas above).

> **Previously on Hugging Face.** This step used to run `Qwen/Qwen3-VL-*` through the
> HF Inference router. If you ever go back: pin the provider explicitly
> (`provider="novita"`) rather than `"auto"`, because several vision models are *also*
> listed on text-only providers (e.g. `featherless-ai`) — if `auto` routes there the
> image is silently dropped and you get a confusing `Conversation roles must
> alternate ...` error. `google/gemma-3-27b-it` is text-only on every HF provider; use
> a `*-VL` model. `HF_TOKEN` is no longer needed for the current code path.

## License

Internal tooling — not for redistribution.
