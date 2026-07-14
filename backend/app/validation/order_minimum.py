"""Server-side order-minimum validation — the authority (PRD §6).

Rules:
- ≥ 18 pieces total
- ≥ 4 pieces per style (summed across colors)
- ≥ 2 pieces per SKU (a size cell within a style+color), EXCEPT that single
  pieces are allowed once the style already meets its 4-piece minimum
  ("additional singles" clause, PRD §6 — implemented reading confirmed
  2026-07-15, pending Prada's final word)
- No pre-packs (nothing to validate: the form simply offers no pre-pack option)

Returns structured errors so the frontend can highlight offending rows.
"""
from typing import Any

MIN_TOTAL = 18
MIN_PER_STYLE = 4
MIN_PER_SKU = 2

SIZE_LABELS = {"qty_xs": "X/S", "qty_sm": "S/M", "qty_ml": "M/L"}


def validate_minimums(items: list[Any]) -> list[dict[str, Any]]:
    """`items` have .style_name, .color, .qty_xs, .qty_sm, .qty_ml (all ≥ 0)."""
    errors: list[dict[str, Any]] = []

    style_totals: dict[str, int] = {}
    for it in items:
        pieces = it.qty_xs + it.qty_sm + it.qty_ml
        if pieces:
            style_totals[it.style_name] = style_totals.get(it.style_name, 0) + pieces

    total = sum(style_totals.values())
    if total < MIN_TOTAL:
        errors.append(
            {
                "code": "min_total",
                "message": f"Order total is {total} pieces — the minimum is {MIN_TOTAL}.",
            }
        )

    for style, pieces in style_totals.items():
        if pieces < MIN_PER_STYLE:
            errors.append(
                {
                    "code": "min_style",
                    "style": style,
                    "message": f'"{style}" has {pieces} piece(s) — each style needs at least {MIN_PER_STYLE}.',
                }
            )

    for it in items:
        for attr, label in SIZE_LABELS.items():
            n = getattr(it, attr)
            if 0 < n < MIN_PER_SKU and style_totals.get(it.style_name, 0) < MIN_PER_STYLE:
                errors.append(
                    {
                        "code": "min_sku",
                        "style": it.style_name,
                        "color": it.color,
                        "size": label,
                        "message": (
                            f'"{it.style_name} — {it.color}" {label} has {n} piece — '
                            f"minimum {MIN_PER_SKU} per size until the style reaches {MIN_PER_STYLE}."
                        ),
                    }
                )

    return errors
