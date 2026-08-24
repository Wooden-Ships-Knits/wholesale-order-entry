"""Send each candidate to an LLM and check what comes back.

The prompt is not written here. It is read from `prompt.md`, so the document
that explains the judgement and the code that performs it cannot drift apart.

Every answer is checked against the candidate it was about before it is kept:
a brand the store does not carry means the model invented it, and an invented
answer is rejected rather than repaired — a model that invents once will invent
again, and the repaired version reads just as convincing.

  export OPENAI_API_KEY=...
  PYTHONPATH=src python analysis/judge.py data/llm [--model gpt-4o-mini] [--limit N]

Writes verdicts.jsonl beside the inputs and prints a summary.
"""
import argparse
import csv
import json
import os
import pathlib
import re
import sys
from collections import Counter

DEFAULT_MODEL = "gpt-4o-mini"
PROMPT_FILE = pathlib.Path(__file__).with_name("prompt.md")
PLACEHOLDER = "{contents of pattern.json}"
VERDICTS = ("strong", "possible", "weak", "insufficient_data")

# The model is told to answer JSON only, and mostly does. This catches the rest.
_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.S)
# A brand shows up as a run of all-caps words. Matching a character class that
# includes spaces would cut "BU C" out of "The BU Club", so tokens are taken
# whole and only joined when they are genuinely adjacent.
_TOKEN_RE = re.compile(r"[A-Za-z0-9&'.\-]+")
# An apostrophe belongs inside K'LANI but not around a quoted 'GIVEX'.
_EDGE_PUNCT = "'\".-"
MIN_NAME_LETTERS = 4     # below this it is an initialism, not a brand worth flagging


def _prompt_template(path=PROMPT_FILE):
    """The system message, lifted from the '## System message' block of prompt.md."""
    text = path.read_text(encoding="utf-8")
    body = text.split("## System message", 1)[1]
    return body.split("````")[1].strip()


def system_message(pattern, path=PROMPT_FILE):
    """The prompt with this run's pattern substituted in."""
    template = _prompt_template(path)
    if PLACEHOLDER not in template:
        raise ValueError(f"{path.name} no longer contains {PLACEHOLDER!r}")
    return template.replace(PLACEHOLDER, json.dumps(pattern, indent=1))


# Words an answer may shout without naming a brand: the payload's own field
# names and the verdict values the model was asked to return. Without these the
# check cries wolf at a model explaining its reasoning, and a check that cries
# wolf stops being read.
_SCHEMA_WORDS = frozenset(w for phrase in (
    "domain catalogue_size brand_count products_per_brand store_type top_brands "
    "category_mix signature_tags_carried tag_lift price_p25_p50_p75 price_range "
    "knitwear_share knitwear_price_median about_text verdict confidence reasons "
    "for_the_rep against json multi_brand house_brand insufficient_data "
    "strong possible weak knit knitwear price band shelf store label"
).split() for w in phrase.upper().split("_"))


def _named_terms(answer):
    """Runs of all-caps words from the free text, which is how a brand appears."""
    text = " ".join([*(answer.get("reasons") or []),
                     answer.get("for_the_rep") or "",
                     answer.get("against") or ""])
    terms, run = set(), []
    for raw in _TOKEN_RE.findall(text):
        token = raw.strip(_EDGE_PUNCT)
        if token and token.isupper() and any(c.isalpha() for c in token):
            run.append(token)
            continue
        if run:
            terms.add(" ".join(run))
            run = []
    if run:
        terms.add(" ".join(run))
    return {t for t in terms
            if sum(c.isalnum() for c in t) >= MIN_NAME_LETTERS}


def check(answer, candidate):
    """Everything wrong with this answer, as plain sentences. Empty means clean.

    Runs before the answer is trusted, because the failures worth catching are
    the ones that read fine: an invented brand, or a store that buys from nobody
    talked up into a prospect.
    """
    problems = []

    allowed = {b.upper() for b in candidate.get("top_brands") or []}
    allowed |= {t.upper() for t in candidate.get("signature_tags_carried") or []}
    # The store's own word for the thing we make. Absent from the signature for
    # a shop that describes its stock in its own vocabulary, and the model is
    # asked to cite it, so leaving it out here would flag a true sentence.
    allowed |= {t.upper() for t in candidate.get("knit_tags_carried") or []}
    allowed |= {c.upper() for c in candidate.get("category_mix") or {}}
    for term in _named_terms(answer):
        if term in allowed:
            continue
        # Only flag a term that looks like a name, not an ordinary shouted word.
        if any(term in a or a in term for a in allowed):
            continue
        if set(term.split()) <= _SCHEMA_WORDS:
            continue
        if len(term.split()) <= 4 and term.isupper():
            problems.append(f"names {term!r}, which is not on this store's shelf")

    verdict = answer.get("verdict")
    if verdict not in VERDICTS:
        problems.append(f"verdict {verdict!r} is not one of {', '.join(VERDICTS)}")

    unreadable = (candidate.get("catalogue_size") == 0
                  or candidate.get("store_type") == "insufficient_data")
    if unreadable and verdict != "insufficient_data":
        problems.append("store is unreadable, so the verdict must be insufficient_data")
    elif candidate.get("store_type") == "house_brand" and verdict != "weak":
        problems.append("store_type is house_brand, so the verdict must be weak")
    # Rule 2, enforced rather than left to the model. Ordered last of the three
    # because the two above are sharper reasons for the same answer, and a row
    # carrying both objections tells a reader to fix one thing twice.
    #
    # `== "none"` rather than a falsy test: a payload written before this field
    # existed has no answer to give, and treating its silence as "no knitwear"
    # would fail every row of it.
    #
    # `insufficient_data` is exempt, and the exemption matters. skip_reason
    # deliberately does NOT gate a shop whose catalogue is too thin to read --
    # "filing it under no knitwear would state something about a shelf nobody
    # managed to see" -- so such a shop reaches the model, honestly answers
    # insufficient_data, and was then flagged for breaking a rule it obeyed.
    # Measured on one run: 83 rows carried that false mark, every one of them a
    # correct answer wearing a "do not trust this row" badge.
    elif (candidate.get("knit_evidence") == "none"
          and verdict not in ("weak", "insufficient_data")):
        problems.append("nothing in the catalogue names knitwear, so the verdict "
                        "must be weak")

    return problems


# What each hard rule says the verdict must be. `check` names the rule in
# prose; this is the same fact in a form code can act on.
FORCED = {
    "store is unreadable": "insufficient_data",
    "store_type is house_brand": "weak",
    "nothing in the catalogue names knitwear": "weak",
}


def enforce(answer, problems):
    """Apply the verdict a hard rule names, rather than only complaining.

    `check` used to record "store_type is house_brand, so the verdict must be
    weak" and leave the model's `strong` standing. Nothing downstream read
    `problems` -- it is not filtered, sorted or re-queued on -- so a flagged
    `strong` still reached the top of a rep's call list. A rule that cannot
    change an answer is a comment, and prompt.md's own guidance is that an
    absolute rule belongs in code.

    The hallucination and bad-verdict findings are NOT enforced: there is no
    correct verdict to substitute for an invented brand, and the right response
    to those is still to distrust the whole answer.
    """
    for prefix, verdict in FORCED.items():
        if any(p.startswith(prefix) for p in problems):
            return {**answer, "verdict": verdict, "confidence": "high"}
    return answer


# Worst first, so the top of the file is the work. A rep opening this reads
# down until the calls run out, not around looking for the good ones.
CALL_ORDER = {"strong": 0, "possible": 1, "weak": 2, "insufficient_data": 3}

VERDICT_COLUMNS = [
    "domain", "verdict", "confidence", "for_the_rep", "reasons", "against",
    "store_type", "brand_count", "products_per_brand", "tag_lift",
    "price_median", "price_range", "knitwear_share", "knitwear_price_median",
    "signature_tags_carried", "top_brands", "problems",
]


def verdict_rows(results, candidates):
    """One flat row per judged store: the verdict, and the facts behind it.

    The facts are copied in rather than left in candidates.jsonl, so the file
    opens in a spreadsheet and answers on its own. A rep reading it should never
    need a second file to see why a store was called.
    """
    join = lambda xs: "; ".join(str(x) for x in xs if x not in (None, ""))  # noqa: E731

    rows = []
    for r in results:
        c = candidates.get(r.get("domain")) or {}
        prices = c.get("price_p25_p50_p75") or [None, None, None]
        rows.append({
            "domain": r.get("domain") or "",
            "verdict": r.get("verdict") or "",
            "confidence": r.get("confidence") or "",
            "for_the_rep": r.get("for_the_rep") or "",
            "reasons": join(r.get("reasons") or []),
            "against": r.get("against") or "",
            "store_type": c.get("store_type") or "",
            "brand_count": c.get("brand_count", ""),
            "products_per_brand": c.get("products_per_brand", ""),
            "tag_lift": c.get("tag_lift", ""),
            "price_median": prices[1] if prices[1] is not None else "",
            "price_range": c.get("price_range", "") if c.get("price_range") is not None else "",
            "knitwear_share": c.get("knitwear_share", ""),
            "knitwear_price_median": (c.get("knitwear_price_median")
                                      if c.get("knitwear_price_median") is not None else ""),
            "signature_tags_carried": join(c.get("signature_tags_carried") or []),
            "top_brands": join((c.get("top_brands") or [])[:8]),
            "problems": join(r.get("problems") or []),
        })
    rows.sort(key=lambda row: (CALL_ORDER.get(row["verdict"], 9), row["domain"]))
    return rows


def write_verdict_csv(path, results, candidates):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=VERDICT_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(verdict_rows(results, candidates))
    return path


def parse(text):
    """The answer as a dict, or None when the model did not return JSON."""
    stripped = _FENCE_RE.sub(r"\1", text or "")
    try:
        answer = json.loads(stripped)
    except (ValueError, TypeError):
        return None
    return answer if isinstance(answer, dict) else None


def judge_one(candidate, pattern, complete, system=None):
    """Judge one candidate, keeping the answer and whatever is wrong with it.

    `system` is accepted so a caller judging many stores builds the prompt once;
    it is the only expensive part of the setup and it does not vary per store.
    """
    system = system if system is not None else system_message(pattern)
    raw = complete(system, json.dumps(candidate, ensure_ascii=False))
    answer = parse(raw)
    if answer is None:
        return {"domain": candidate.get("domain"), "verdict": None,
                "problems": ["answer was not JSON"], "raw": raw}
    problems = check(answer, candidate)
    return {"domain": candidate.get("domain"),
            **enforce(answer, problems),
            "problems": problems}


def judge(pattern, candidates, complete):
    """Judge every candidate, keeping the answer and whatever is wrong with it.

    `complete(system, user) -> str` is injected so the run can be tested without
    a network or a key.
    """
    system = system_message(pattern)
    return [judge_one(c, pattern, complete, system=system) for c in candidates]


def openai_completer(model=DEFAULT_MODEL, api_key=None):
    """A `complete` callable backed by the OpenAI API.

    Imported here rather than at module scope so the tests, and anyone reading
    the checks, need neither the package nor a key.
    """
    from openai import OpenAI

    key = api_key or os.environ.get("OPENAI_API_KEY")
    if not key:
        sys.exit("OPENAI_API_KEY is not set. export it, or pass --api-key-file.")
    client = OpenAI(api_key=key)

    def complete(system, user):
        response = client.chat.completions.create(
            model=model,
            temperature=0,          # the same store must not get two answers
            response_format={"type": "json_object"},
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
        )
        return response.choices[0].message.content
    return complete


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("llm_dir", nargs="?", default="data/llm",
                    help="directory holding pattern.json and candidates.jsonl")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--limit", type=int, help="judge only the first N candidates")
    ap.add_argument("--api-key-file", help="read the key from a file instead of the env")
    ap.add_argument("--export-only", action="store_true",
                    help="rebuild the CSV from an existing verdicts.jsonl, calling nothing")
    ap.add_argument("--dump-prompt", action="store_true",
                    help="write the prompt with the pattern filled in, for review")
    args = ap.parse_args(argv)

    d = pathlib.Path(args.llm_dir)
    pattern = json.loads((d / "pattern.json").read_text(encoding="utf-8"))
    candidates = [json.loads(line) for line in
                  (d / "candidates.jsonl").read_text(encoding="utf-8").splitlines() if line]
    if args.limit:
        candidates = candidates[:args.limit]

    if args.dump_prompt:
        # prompt.md is a template with a placeholder in it, which reads as an
        # unfinished document to anyone who did not write it. This is the thing
        # the model was actually handed.
        path = d / "prompt-as-sent.md"
        example = candidates[0] if candidates else {}
        path.write_text(
            "# Prompt as sent\n\n"
            "The two messages the model receives. The system message goes once\n"
            "per conversation; the user message is one store, and there is one of\n"
            f"them per candidate ({len(candidates)} in this run).\n\n"
            "The store below is indented so it can be read. On the wire it is one\n"
            "line — whitespace is the only difference between this document and\n"
            "what was sent.\n\n"
            "## System message\n\n````\n" + system_message(pattern) + "\n````\n\n"
            "## User message — one example of "
            f"{len(candidates)}\n\n````json\n"
            + json.dumps(example, indent=1, ensure_ascii=False) + "\n````\n",
            encoding="utf-8")
        print(f"wrote the resolved prompt to {path}")
        return

    out = d / "verdicts.jsonl"
    if args.export_only:
        # Judging costs money; reshaping what it already returned does not.
        results = [json.loads(line) for line in
                   out.read_text(encoding="utf-8").splitlines() if line]
        print(f"exporting {len(results)} existing verdicts, calling nothing")
    else:
        key = None
        if args.api_key_file:
            key = pathlib.Path(args.api_key_file).read_text(encoding="utf-8").strip()

        print(f"judging {len(candidates)} stores with {args.model}", flush=True)
        complete = openai_completer(args.model, key)

        results = []
        for i, candidate in enumerate(candidates, 1):
            print(f"[{i}/{len(candidates)}] {candidate.get('domain')}", flush=True)
            results.extend(judge(pattern, [candidate], complete))

        with open(out, "w", encoding="utf-8") as fh:
            for r in results:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    by_domain = {c.get("domain"): c for c in candidates}
    csv_path = write_verdict_csv(d / "verdicts.csv", results, by_domain)

    counts = Counter(r.get("verdict") for r in results)
    rejected = [r for r in results if r.get("problems")]
    if not args.export_only:
        print(f"\nwrote {len(results)} verdicts to {out}")
    print(f"wrote {len(results)} rows to {csv_path}")
    for v, n in counts.most_common():
        print(f"   {str(v):<20}{n:>4}")
    print(f"\nanswers failing their own check: {len(rejected)}")
    for r in rejected[:10]:
        print(f"   {r['domain']}: {'; '.join(r['problems'])}")

    # The failure to watch for is agreement, not error: a judge that likes
    # everything has told you nothing, and it looks like success.
    if counts.get("strong", 0) == len(results) and results:
        print("\nWARNING: every store came back 'strong'. That is the model agreeing "
              "with you, not judging. Plant a known-bad store and run again.")


if __name__ == "__main__":
    main()
