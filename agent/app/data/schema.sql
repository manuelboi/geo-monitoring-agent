-- Rebuilt from scratch by the loader on every start, inside one transaction.
-- geo: normalised tables, written only by the loader.
-- api: views, the only objects the agent's read-only role can see.

CREATE SCHEMA geo;
CREATE SCHEMA api;

CREATE TABLE geo.prompts (
    prompt_id  text PRIMARY KEY,
    query_it   text NOT NULL,
    label_en   text NOT NULL,
    theme      text NOT NULL,
    buyer_type text NOT NULL
);

CREATE TABLE geo.answers (
    answer_id      text PRIMARY KEY,
    wave_date      date NOT NULL,
    ai_system      text NOT NULL,
    prompt_id      text NOT NULL REFERENCES geo.prompts,
    answer_text_it text NOT NULL,
    UNIQUE (wave_date, ai_system, prompt_id)
);

CREATE TABLE geo.brands (
    brand_name    text PRIMARY KEY,
    brand_website text,
    is_target     boolean NOT NULL
);

CREATE TABLE geo.mentions (
    mention_id            text PRIMARY KEY,
    answer_id             text NOT NULL REFERENCES geo.answers,
    brand_name            text NOT NULL REFERENCES geo.brands,
    brand_name_as_written text NOT NULL,
    position              integer NOT NULL CHECK (position >= 1),
    sentiment             text NOT NULL CHECK (sentiment IN ('positive', 'neutral', 'negative')),
    UNIQUE (answer_id, position)
);

-- One row per cited source. Its attributes depend on citation_id alone (verified by profile.py).
CREATE TABLE geo.citations (
    citation_id              text PRIMARY KEY,
    source_domain            text,
    source_type              text NOT NULL,
    content_format           text NOT NULL,
    content_ownership        text NOT NULL,
    content_url              text,
    author                   text,
    publication_date         date,
    source_also_cites_target boolean NOT NULL
);

-- A source can support several mentions: this is the citations sheet's row grain.
CREATE TABLE geo.mention_citations (
    mention_id  text NOT NULL REFERENCES geo.mentions,
    citation_id text NOT NULL REFERENCES geo.citations,
    PRIMARY KEY (mention_id, citation_id)
);
CREATE INDEX ON geo.mention_citations (citation_id);

CREATE TABLE geo.kpi_definitions (
    kpi        text PRIMARY KEY,
    definition text NOT NULL,
    formula    text NOT NULL,
    example    text NOT NULL
);

CREATE TABLE geo.context (
    item  text PRIMARY KEY,
    value text NOT NULL
);

CREATE INDEX ON geo.answers (prompt_id);
CREATE INDEX ON geo.mentions (answer_id);
CREATE INDEX ON geo.mentions (brand_name);

CREATE VIEW api.v_prompts AS
SELECT prompt_id, query_it, label_en, theme, buyer_type
FROM geo.prompts;

-- Includes the answers that name no brand: they count in visibility and prominence denominators.
CREATE VIEW api.v_answers AS
SELECT a.answer_id, a.wave_date, a.ai_system, a.prompt_id,
       p.query_it, p.label_en, p.theme, p.buyer_type,
       a.answer_text_it,
       (SELECT count(DISTINCT m.brand_name) FROM geo.mentions m WHERE m.answer_id = a.answer_id) AS n_brands_mentioned,
       (SELECT m.brand_name FROM geo.mentions m WHERE m.answer_id = a.answer_id AND m.position = 1) AS first_brand_named
FROM geo.answers a
JOIN geo.prompts p USING (prompt_id);

CREATE VIEW api.v_mentions AS
SELECT m.mention_id, m.answer_id, a.wave_date, a.ai_system, a.prompt_id,
       p.label_en, p.theme, p.buyer_type,
       m.brand_name, m.brand_name_as_written, b.brand_website, b.is_target,
       m.position, m.sentiment
FROM geo.mentions m
JOIN geo.answers a USING (answer_id)
JOIN geo.prompts p USING (prompt_id)
JOIN geo.brands b USING (brand_name);

-- Same grain as the citations sheet: one row per citation x mention.
CREATE VIEW api.v_citations AS
SELECT c.citation_id, mc.mention_id, m.answer_id, m.wave_date, m.ai_system, m.prompt_id,
       m.theme, m.buyer_type, m.brand_name, m.is_target,
       c.source_domain, c.source_type, c.content_format, c.content_ownership,
       c.content_url, c.author, c.publication_date, c.source_also_cites_target
FROM geo.mention_citations mc
JOIN geo.citations c USING (citation_id)
JOIN api.v_mentions m USING (mention_id);

CREATE VIEW api.v_kpi_definitions AS
SELECT kpi, definition, formula, example FROM geo.kpi_definitions;

CREATE VIEW api.v_context AS
SELECT item, value FROM geo.context;
