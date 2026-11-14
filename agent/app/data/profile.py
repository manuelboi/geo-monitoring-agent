"""Checks the assumptions the schema relies on, before anything is loaded.

Usage: python -m app.data.profile [data_dir]   (default data_dir: /data)
"""

import csv
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

LEADER = "Brand Alpha"


def read(data_dir: Path, name: str) -> list[dict]:
    with open(data_dir / "csv" / name, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def report(label: str, problems: list) -> None:
    print(f"[{'OK  ' if not problems else 'FAIL'}] {label}")
    for p in problems[:5]:
        print(f"         {p}")
    if len(problems) > 5:
        print(f"         ... {len(problems) - 5} more")


def varying(rows: list[dict], key: str, columns: list[str]) -> list[str]:
    """Columns whose value differs between rows that share the same key."""
    values = defaultdict(lambda: defaultdict(set))
    for r in rows:
        for c in columns:
            values[r[key]][c].add(r[c])
    return [f"{k}: {c}={sorted(v)}" for k, cols in values.items() for c, v in cols.items() if len(v) > 1]


def duplicates(rows: list[dict], *columns: str) -> list:
    counts = Counter(tuple(r[c] for c in columns) for r in rows)
    return [k for k, n in counts.items() if n > 1]


def main(data_dir: Path) -> None:
    prompts = read(data_dir, "04_prompts.csv")
    answers = read(data_dir, "05_answers.csv")
    mentions = read(data_dir, "06_mentions.csv")
    citations = read(data_dir, "07_citations.csv")

    print("== Row counts and keys")
    expected = {
        "prompts": (prompts, 8),
        "answers": (answers, 32),
        "mentions": (mentions, 64),
        "citations": (citations, 64),
    }
    report("row counts match the catalog", [f"{n}: {len(r)} != {e}" for n, (r, e) in expected.items() if len(r) != e])
    report("prompt_id unique", duplicates(prompts, "prompt_id"))
    report("answer_id unique", duplicates(answers, "answer_id"))
    report("mention_id unique", duplicates(mentions, "mention_id"))
    report("citation_id + mention_id unique", duplicates(citations, "citation_id", "mention_id"))
    print(f"       citation_id alone: {len({c['citation_id'] for c in citations})} distinct over {len(citations)} rows")

    print("== Relationships")
    prompt_by_id = {p["prompt_id"]: p for p in prompts}
    answer_by_id = {a["answer_id"]: a for a in answers}
    mention_by_id = {m["mention_id"]: m for m in mentions}
    report(
        "answers.prompt_id exists in prompts", [a["answer_id"] for a in answers if a["prompt_id"] not in prompt_by_id]
    )
    report(
        "mentions.answer_id exists in answers",
        [m["mention_id"] for m in mentions if m["answer_id"] not in answer_by_id],
    )
    report(
        "citations.mention_id exists in mentions",
        [c["citation_id"] for c in citations if c["mention_id"] not in mention_by_id],
    )

    print("== Repeated columns agree with their source table")
    report(
        "answer_id = <prompt_id>-<ai_system>",
        [a["answer_id"] for a in answers if a["answer_id"] != f"{a['prompt_id']}-{a['ai_system']}"],
    )
    report(
        "answers.query_it = prompts.query_it",
        [a["answer_id"] for a in answers if a["query_it"] != prompt_by_id[a["prompt_id"]]["query_it"]],
    )
    report(
        "mentions: wave_date, ai_system, prompt_id = answer's",
        [
            m["mention_id"]
            for m in mentions
            if any(m[c] != answer_by_id[m["answer_id"]][c] for c in ("wave_date", "ai_system", "prompt_id"))
        ],
    )
    report(
        "citations: answer_id, brand_name, is_target = mention's",
        [
            f"{c['citation_id']}/{c['mention_id']}"
            for c in citations
            if any(c[k] != mention_by_id[c["mention_id"]][k] for k in ("answer_id", "brand_name", "is_target"))
        ],
    )
    report(
        "citations: wave_date, ai_system, prompt_id = answer's",
        [
            f"{c['citation_id']}/{c['mention_id']}"
            for c in citations
            if any(c[k] != answer_by_id[c["answer_id"]][k] for k in ("wave_date", "ai_system", "prompt_id"))
        ],
    )

    print("== Brands")
    report(
        "brand_website and is_target constant per brand_name",
        varying(mentions, "brand_name", ["brand_website", "is_target"]),
    )
    by_lower = defaultdict(set)
    for m in mentions:
        by_lower[m["brand_name"].strip().lower()].add(m["brand_name"])
    report("no brand_name differing only by case or spaces", [sorted(v) for v in by_lower.values() if len(v) > 1])
    targets = sorted({m["brand_name"] for m in mentions if m["is_target"] == "TRUE"})
    print(f"       target brands: {targets}; distinct brands: {len({m['brand_name'] for m in mentions})}")
    same_answer = duplicates(mentions, "answer_id", "brand_name")
    print(f"       brand named twice in the same answer: {len(same_answer)} cases {same_answer[:3]}")
    print(f"       mentions without brand_website: {sum(1 for m in mentions if not m['brand_website'])}")

    print("== Citations")
    citation_columns = [
        "source_domain",
        "source_type",
        "content_format",
        "content_ownership",
        "content_url",
        "author",
        "publication_date",
        "source_also_cites_target",
    ]
    report("citation attributes constant per citation_id", varying(citations, "citation_id", citation_columns))
    no_source = [c for c in citations if c["content_ownership"] == "Model internal knowledge"]
    report(
        "'Model internal knowledge' <=> empty source_domain and content_url",
        [
            f"{c['citation_id']}/{c['mention_id']}"
            for c in citations
            if (c["content_ownership"] == "Model internal knowledge")
            != (c["source_domain"] == "" and c["content_url"] == "")
        ],
    )
    print(f"       rows without a source: {len(no_source)}")
    per_mention = Counter(c["mention_id"] for c in citations)
    report(
        "mentions.n_citations = citation rows of the mention",
        [
            f"{m['mention_id']}: {m['n_citations']} vs {per_mention[m['mention_id']]}"
            for m in mentions
            if int(m["n_citations"]) != per_mention[m["mention_id"]]
        ],
    )
    report(
        "every mention has at least one citation",
        [m["mention_id"] for m in mentions if per_mention[m["mention_id"]] == 0],
    )
    domain_owners = defaultdict(set)
    for c in citations:
        if c["source_domain"]:
            domain_owners[c["source_domain"]].add(c["content_ownership"])
    mixed = {d: sorted(o) for d, o in domain_owners.items() if len(o) > 1}
    print(f"       domains with more than one content_ownership: {len(mixed)} e.g. {list(mixed.items())[:3]}")

    print("== Answer summary columns vs recomputed values")
    mentions_of = defaultdict(list)
    for m in mentions:
        mentions_of[m["answer_id"]].append(m)
    citations_of = defaultdict(list)
    for c in citations:
        citations_of[c["answer_id"]].append(c)

    def position_of(answer_id: str, predicate) -> str:
        positions = [int(m["position"]) for m in mentions_of[answer_id] if predicate(m)]
        return str(min(positions)) if positions else ""

    recomputed = {
        "n_brands_mentioned": lambda a: str(len({m["brand_name"] for m in mentions_of[a]})),
        "first_brand_named": lambda a: next((m["brand_name"] for m in mentions_of[a] if m["position"] == "1"), ""),
        "target_mentioned": lambda a: "TRUE" if any(m["is_target"] == "TRUE" for m in mentions_of[a]) else "FALSE",
        "target_position": lambda a: position_of(a, lambda m: m["is_target"] == "TRUE"),
        "leader_mentioned": lambda a: "TRUE" if any(m["brand_name"] == LEADER for m in mentions_of[a]) else "FALSE",
        "leader_position": lambda a: position_of(a, lambda m: m["brand_name"] == LEADER),
        "n_citations": lambda a: str(len({c["citation_id"] for c in citations_of[a]})),
        "n_distinct_source_domains": lambda a: str(
            len({c["source_domain"] for c in citations_of[a] if c["source_domain"]})
        ),
    }
    for column, compute in recomputed.items():
        report(
            f"answers.{column}",
            [
                f"{a['answer_id']}: file={a[column]!r} recomputed={compute(a['answer_id'])!r}"
                for a in answers
                if a[column] != compute(a["answer_id"])
            ],
        )
    print(f"       answers without mentions: {[a['answer_id'] for a in answers if not mentions_of[a['answer_id']]]}")

    print("== Values and types")
    report(
        "sentiment in positive/neutral/negative",
        sorted({m["sentiment"] for m in mentions} - {"positive", "neutral", "negative"}),
    )
    booleans = (
        [(r, c) for r in answers for c in ("target_mentioned", "leader_mentioned")]
        + [(r, "is_target") for r in mentions]
        + [(r, c) for r in citations for c in ("is_target", "source_also_cites_target")]
    )
    report("booleans are TRUE/FALSE", sorted({r[c] for r, c in booleans} - {"TRUE", "FALSE"}))
    bad_dates = []
    for r, c in [(a, "wave_date") for a in answers] + [
        (c, "publication_date") for c in citations if c["publication_date"]
    ]:
        try:
            date.fromisoformat(r[c])
        except ValueError:
            bad_dates.append(r[c])
    report("dates are ISO YYYY-MM-DD", bad_dates)
    report(
        "positions are integers >= 1",
        [m["mention_id"] for m in mentions if not m["position"].isdigit() or int(m["position"]) < 1],
    )
    gaps = []
    for answer_id, ms in mentions_of.items():
        positions = sorted(int(m["position"]) for m in ms)
        if positions != list(range(1, len(positions) + 1)):
            gaps.append(f"{answer_id}: {positions}")
    report("positions in each answer are 1..n without gaps or ties", gaps)
    stripped = [
        f"{name}.{c}"
        for name, (rows, _) in expected.items()
        for r in rows
        for c, v in r.items()
        if isinstance(v, str) and v != v.strip() and c != "answer_text_it"
    ]
    report("no leading/trailing spaces in values", sorted(set(stripped)))

    print("== Categorical values (useful for the agent prompt)")
    for name, rows, column in [
        ("prompts", prompts, "theme"),
        ("prompts", prompts, "buyer_type"),
        ("answers", answers, "ai_system"),
        ("answers", answers, "wave_date"),
        ("citations", citations, "source_type"),
        ("citations", citations, "content_ownership"),
        ("citations", citations, "content_format"),
    ]:
        print(f"       {name}.{column}: {dict(Counter(r[column] for r in rows).most_common())}")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/data"))
