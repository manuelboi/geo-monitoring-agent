import csv
from datetime import date, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CSV_DIR = ROOT / "data" / "csv"
SYSTEMS = ["ChatGPT", "Claude", "Gemini", "Perplexity"]
WAVE = "2025-01-01"
BRANDS = ["Sample Client", "Brand Alpha", "Brand Beta", "Brand Gamma"]


def write_csv(name: str, columns: list[str], rows: list[dict[str, str]]) -> None:
    with (CSV_DIR / name).open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    CSV_DIR.mkdir(parents=True, exist_ok=True)
    prompts = [
        {
            "prompt_id": f"P{i:02d}",
            "query_it": f"Quali brand compaiono nel tema sintetico {i:02d}?",
            "label_en": f"Synthetic prompt {i:02d}",
            "theme": f"Theme {(i - 1) % 2 + 1}",
            "buyer_type": f"Buyer type {(i - 1) % 2 + 1}",
        }
        for i in range(1, 9)
    ]

    mentions: list[dict[str, str]] = []
    answers: list[dict[str, str]] = []
    citations: list[dict[str, str]] = []

    for prompt in prompts:
        for system in SYSTEMS:
            answer_number = len(answers)
            answer_id = f"{prompt['prompt_id']}-{system}"
            if answer_number % 4 == 0:
                names = ["Sample Client", "Brand Alpha"]
            elif answer_number % 4 == 1:
                names = ["Brand Alpha", "Sample Client"]
            elif answer_number % 4 == 2:
                names = ["Brand Alpha", "Brand Beta"]
            else:
                names = ["Brand Alpha", "Brand Gamma"]

            answer_mentions = []
            answer_citations = []
            for position, brand in enumerate(names, start=1):
                mention_number = len(mentions) + 1
                citation_number = (mention_number - 1) % 48 + 1
                citation_id = f"C{citation_number:03d}"
                is_target = brand == "Sample Client"
                mention = {
                    "mention_id": f"M{mention_number:03d}",
                    "answer_id": answer_id,
                    "wave_date": WAVE,
                    "ai_system": system,
                    "prompt_id": prompt["prompt_id"],
                    "brand_name": brand,
                    "brand_name_as_written": brand,
                    "brand_website": f"https://brand-{BRANDS.index(brand) + 1:02d}.example",
                    "position": str(position),
                    "sentiment": ("positive", "neutral", "negative")[(answer_number + position) % 3],
                    "is_target": "TRUE" if is_target else "FALSE",
                    "n_citations": "1",
                }
                mentions.append(mention)
                answer_mentions.append(mention)

                ownership = ("Owned", "Earned", "Model internal knowledge", "User generated")[
                    (citation_number - 1) % 4
                ]
                sourced = ownership != "Model internal knowledge"
                source_domain = f"source-{citation_number:02d}.example" if sourced else ""
                content_url = f"https://{source_domain}/item-{citation_number:02d}" if sourced else ""
                publication_date = (
                    (date(2024, 1, 1) + timedelta(days=citation_number)).isoformat() if sourced else ""
                )
                citation = {
                    "citation_id": citation_id,
                    "mention_id": mention["mention_id"],
                    "answer_id": answer_id,
                    "wave_date": WAVE,
                    "ai_system": system,
                    "prompt_id": prompt["prompt_id"],
                    "brand_name": brand,
                    "is_target": mention["is_target"],
                    "source_domain": source_domain,
                    "source_type": ("Synthetic publication", "Synthetic directory")[citation_number % 2],
                    "content_format": ("Article", "Listing")[citation_number % 2],
                    "content_ownership": ownership,
                    "content_url": content_url,
                    "author": f"Synthetic Author {citation_number:02d}" if sourced else "",
                    "publication_date": publication_date,
                    "source_also_cites_target": "TRUE" if citation_number % 3 == 0 else "FALSE",
                }
                citations.append(citation)
                answer_citations.append(citation)
            first = names[0]
            target_positions = [
                int(m["position"]) for m in answer_mentions if m["is_target"] == "TRUE"
            ]
            leader_positions = [
                int(m["position"]) for m in answer_mentions if m["brand_name"] == "Brand Alpha"
            ]
            source_domains = {c["source_domain"] for c in answer_citations if c["source_domain"]}
            answers.append(
                {
                    "answer_id": answer_id,
                    "wave_date": WAVE,
                    "ai_system": system,
                    "prompt_id": prompt["prompt_id"],
                    "query_it": prompt["query_it"],
                    "answer_text_it": f"Risposta sintetica: {names[0]} e {names[1]} sono citati.",
                    "n_brands_mentioned": str(len(set(names))),
                    "first_brand_named": first,
                    "target_mentioned": "TRUE" if target_positions else "FALSE",
                    "target_position": str(min(target_positions)) if target_positions else "",
                    "leader_mentioned": "TRUE" if leader_positions else "FALSE",
                    "leader_position": str(min(leader_positions)) if leader_positions else "",
                    "n_citations": str(len({c["citation_id"] for c in answer_citations})),
                    "n_distinct_source_domains": str(len(source_domains)),
                }
            )

    context_items = [
        ("Platform", "Synthetic GEO monitoring demonstration"),
        ("Client account", "Sample Client"),
        ("Most visible competitor", "Brand Alpha"),
        ("Who the AI answers are for", "Synthetic buyer roles"),
        ("Who uses the platform", "Synthetic analytics team"),
        ("Geography / language", "Synthetic Italian-language prompts"),
        ("AI assistants monitored", ", ".join(SYSTEMS)),
        ("Prompts", "8 synthetic prompts"),
        ("Answers per wave", "32 synthetic answers"),
        ("Waves", "One synthetic wave"),
        ("Latest wave volume", "32 synthetic answers"),
        ("Data note", "Generated demonstration data; no real client, brand, person, or source data."),
    ]
    kpis = [
        ("Answer", "One synthetic response from one assistant to one prompt.", "Count of answer_id"),
        ("Mention", "A synthetic brand named in an answer.", "Count of mention_id"),
        ("Visibility score", "Share of answers that mention the brand at least once.", "Answers mentioning brand / answers in scope"),
        ("Share of voice", "Brand mentions as a share of all brand mentions in scope.", "Brand mentions / all brand mentions in scope"),
        ("Sentiment score", "Share of brand mentions with positive tone.", "Positive mentions / brand mentions"),
        ("Average position", "Mean rank at which the brand is named inside an answer.", "Mean(position)"),
        ("Top-3 rate", "Share of brand mentions in positions 1 through 3.", "Mentions at positions 1-3 / brand mentions"),
        ("Prominence score", "Visibility weighted by how prominently the brand is named.", "Sum(max(0, (11 - position) / 10)) / answers in scope"),
        ("Citation", "A synthetic source used to support a mention.", "Count of citation rows"),
        ("Content ownership", "Synthetic source ownership category.", "Categorical value"),
        ("Source mix", "Distribution of citations by content ownership.", "Citations of a type / all citations in scope"),
        ("Earned gap domain", "A synthetic earned domain cited for competitors but not the target.", "Distinct qualifying source domains"),
    ]
    dictionary = [
        ("prompts", "prompt_id", "Stable identifier for a synthetic prompt."),
        ("prompts", "query_it", "Synthetic Italian-language prompt text."),
        ("answers", "answer_id", "Prompt and assistant identifier."),
        ("answers", "answer_text_it", "Synthetic Italian-language answer text."),
        ("mentions", "brand_name", "Synthetic brand label."),
        ("mentions", "position", "Synthetic rank within the answer."),
        ("citations", "source_domain", "Reserved example domain for synthetic citations."),
        ("citations", "content_url", "Synthetic URL using the reserved example domain."),
    ]

    write_csv("00_README.csv", ["item", "description"], [
        {"item": "Dataset", "description": "Synthetic demonstration data generated locally."},
        {"item": "Files", "description": "One UTF-8 CSV per table."},
    ])
    write_csv("01_context.csv", ["item", "value"], [
        {"item": item, "value": value} for item, value in context_items
    ])
    write_csv("02_kpi_definitions.csv", ["kpi", "definition", "formula", "example"], [
        {"kpi": kpi, "definition": definition, "formula": formula, "example": "Synthetic example only."}
        for kpi, definition, formula in kpis
    ])
    write_csv("03_data_dictionary.csv", ["sheet", "column", "description"], [
        {"sheet": sheet, "column": column, "description": description}
        for sheet, column, description in dictionary
    ])
    write_csv("04_prompts.csv", ["prompt_id", "query_it", "label_en", "theme", "buyer_type"], prompts)
    write_csv(
        "05_answers.csv",
        [
            "answer_id", "wave_date", "ai_system", "prompt_id", "query_it", "answer_text_it",
            "n_brands_mentioned", "first_brand_named", "target_mentioned", "target_position",
            "leader_mentioned", "leader_position", "n_citations", "n_distinct_source_domains",
        ],
        answers,
    )
    write_csv(
        "06_mentions.csv",
        [
            "mention_id", "answer_id", "wave_date", "ai_system", "prompt_id", "brand_name",
            "brand_name_as_written", "brand_website", "position", "sentiment", "is_target", "n_citations",
        ],
        mentions,
    )
    write_csv(
        "07_citations.csv",
        [
            "citation_id", "mention_id", "answer_id", "wave_date", "ai_system", "prompt_id",
            "brand_name", "is_target", "source_domain", "source_type", "content_format",
            "content_ownership", "content_url", "author", "publication_date", "source_also_cites_target",
        ],
        citations,
    )
    print(f"Generated synthetic data: prompts={len(prompts)}, answers={len(answers)}, "
          f"mentions={len(mentions)}, citation_rows={len(citations)}")


if __name__ == "__main__":
    main()
