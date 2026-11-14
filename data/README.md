# Synthetic data pack

These CSVs are generated locally by `tools/generate_synthetic_data.py`. They contain no client-derived records or
identifiers. The pack includes eight prompts, 32 answers, 64 mentions, and 64 citation rows.

The application loads the CSV files in `csv/` when the `agent` container starts. Citation URLs and domains use the
reserved `.example` domain. Do not replace this pack with real client data.
