# Subtask 14 — Deduplicated report with term filter buttons

**To-do:** new — stop duplicating article cards across per-term sections; render
each retained article **once** in a flat list, tag it with pills for every
matched search term, and add filter buttons along the top to filter the list by
term.
**Decisions:** revises D7 / subtask 12 Q3 (which duplicated cards per term).
Keeps D9 (borderline flag), subtask 12 visual language (cards, bands, chips).
**Depends on:** 05 (`matched_terms` on `Article`), 12 (current card/section UI
+ tests, which this subtask rewrites).

## Problem

Subtask 12 (decision Q3) chose to **duplicate the full card under every matching
term section**: an article matched by 3 terms renders three identical cards in
three separate `<section class="term">` blocks. On the 13 Jul Scopus run this
showed up clearly — a paper appearing under both `game_model` and `style_of_play`
consumed screen real-estate twice, the card count (e.g. "5 cards") exceeded the
unique article count, and a reader had to scroll past the same takeaway / action
points twice. The per-term sections also force a single fixed grouping, so a
reader who wants "all `tracking_data` papers regardless of what else they
matched" still has to visit multiple sections.

The grouping-by-term model made sense when `--limit` was area-wide (only one
term ever had articles). With subtask 13's per-term cap, **every** term section
is populated, so the duplication is now both visible and wasteful.

## Goal

Replace the per-term section layout with a **single flat list of unique
articles**, each card tagged with pills for every search term it matched. Along
the top of the report, render a row of **filter buttons** — one per term (plus
"All") — that filters the list client-side to the articles matching that term.
No article card is rendered more than once.

## Design decisions

| # | Topic | Decision |
|---|-------|----------|
| Q1 | List shape | **Flat, deduplicated, one card per article.** No per-term `<section>` blocks. Order = global score descending (unscored last), replacing the per-term sort. This is the single visible change a reader notices. |
| Q2 | Term tags on cards | **Pills for every matched term, no "current/also" distinction.** The current template marks one pill `.current` and prefixes the rest with "also:". With no section context, all matched terms are equal — render them as identical pills, ordered by `matched_terms` insertion order. Untagged articles get a single muted `Other` pill. |
| Q3 | Filter buttons | **One button per term + an "All" button, along the top** (replacing the sticky sidebar + mobile term-chip row). Single-select: clicking a term shows only articles matching it; "All" clears the filter. The active button is visually highlighted. |
| Q4 | Filter mechanism | **Client-side JS, no re-render.** Each card carries `data-terms="game_model style_of_play"`; clicking a button toggles `hidden` on cards whose `data-terms` does not contain the selected term. Keeps the report a single self-contained static HTML file (no build step, per subtask 12's constraint). |
| Q5 | URL hash | **Sync the active filter to `#term-<slug>`** (and `#all` / no hash = All) so a filtered view is linkable and the browser back button works. Reuses the slug logic already on `TermSection.slug`. On load, apply the filter from the hash if present. |
| Q6 | Per-button counts | **Show the count of unique articles matching each term** on the button (e.g. `game_model (7)`). Because multi-term articles count toward each matching term, the sum of per-term counts can exceed the total — this is correct and informative, not a bug. "All" shows the unique total. |
| Q7 | Untagged articles | **`Other` button + `Other` pill**, same cap/semantics as today. They appear under "All" and under "Other" only. |
| Q8 | Sticky sidebar / mobile chips | **Remove both.** The filter button row replaces the sidebar on desktop and the horizontal term-chip row on mobile. The button row is responsive: wraps on narrow viewports (no horizontal scroll, per subtask 12 Q6). |
| Q9 | Sort order | **Score descending globally.** No interactive sort control (consistent with subtask 12 Q7). When a filter is active, the visible subset keeps the global order — do not re-sort per term. |
| Q10 | Print | **Filter buttons hidden; all cards printed** regardless of the active on-screen filter. Matches subtask 12's print goal (a complete archive). The active filter is an on-screen interaction only. |
| Q11 | Index page | **Unchanged.** Subtask 12 left the index functionally as-is; this subtask does too. |
| Q12 | Empty filter result | **Show a short "No articles match this term" placeholder** when a filter yields zero cards (e.g. a term whose only articles were all dropped by screening). Avoids a blank section. |
| Q13 | Tests | **Rewrite the subtask 12 structure/snapshot tests** for the new shape: assert exactly one card per unique article (no duplicates), a filter button per term + All, `data-terms` on each card, term pills on each card, and a JS filtering smoke test (button click hides non-matching cards). Update the card snapshot; replace the term-section snapshot with a filter-bar snapshot. |
| Q14 | Multi-select filters | **Out of scope.** Single-select only (one term active at a time). Multi-select ("show game_model + tracking_data") is a future enhancement; the `data-terms` attribute is designed so a multi-select upgrade is a JS-only change later. |

## Proposed implementation

1. **`report.py` — replace `build_term_sections` with a flat list + filter metadata.**
   - New helper `build_filterable_articles(articles)` returning
     `(articles_sorted: list[Article], terms: list[TermMeta])` where
     `TermMeta` is `(name, slug, count)` for each distinct matched term in
     first-seen order, plus an `Other` entry if there are untagged articles.
   - Sort `articles_sorted` by score descending globally (unscored last),
     reusing the existing `_sort_key` logic.
   - `TermSection` / `build_term_sections` are removed (or kept but unused —
     prefer removing to avoid drift; update `test_report.py` accordingly).
   - `render_area` passes `articles_sorted` and `terms` to the template
     instead of `sections`.

2. **`templates/area.html.j2` — flat list + filter bar.**
   - Remove the `nav.toc` sidebar, the `.term-chips` mobile row, and the
     `{% for s in sections %}` section loop.
   - Add a `<div class="filters" role="group" aria-label="Filter by search term">`
     row of `<button class="filter-btn" data-term="game_model">game_model (7)</button>`
     buttons (one per term + an `All` button marked active by default).
   - Render one `<article class="card" data-terms="game_model style_of_play">`
     per unique article, in global score order. Keep the existing card
     internals (score badge, category chip, borderline flag, takeaway, why,
     action points, collapsible abstract, copy-citation button).
   - Replace the `.terms-pills` "current / also:" markup with flat pills — one
     per matched term, no `.current` class, no "also:" prefix.
   - Add a `.empty-filter` placeholder element, hidden by default, shown by JS
     when a filter yields no cards.
   - Print CSS: hide `.filters`, show all cards (clear any `hidden` set by JS).

3. **Filter JS (inline `<script>`).**
   - On click of a `.filter-btn`: set active state, update `location.hash`,
     toggle `hidden` on each `article.card` based on whether its `data-terms`
     contains the selected term (or show all for "All"), and toggle the
     `.empty-filter` placeholder.
   - On `hashchange` / load: read `#term-<slug>` and apply the matching filter
     (fall back to "All").
   - No external dependencies; keep the existing copy-citation / abstract /
     print scripts untouched.

4. **Tests — `tests/test_report.py`.**
   - Remove `test_build_term_sections_*`, `test_area_report_has_term_section_headings`,
     `test_area_report_renders_one_card_per_term_membership`,
     `test_area_report_has_sticky_sidebar_and_mobile_term_chips`,
     `test_snapshot_term_section_has_heading_and_anchor`.
   - Add: `test_build_filterable_articles_sorts_globally_by_score`,
     `test_build_filterable_articles_term_counts_dedup_multi_term`,
     `test_area_report_renders_one_card_per_unique_article` (no duplicates),
     `test_area_report_has_filter_button_per_term_plus_all`,
     `test_area_report_card_carries_data_terms_attribute`,
     `test_area_report_term_pills_no_current_distinction`,
     `test_area_report_has_filter_script_and_hash_handler`,
     `test_snapshot_filter_bar_fragment`,
     `test_snapshot_strong_article_card_fragment` (update — card tag now has
     `data-terms`, pills change).
   - The fixture `_sample_articles()` already has a multi-term article (matched
     `game_model` + `style_of_play`) — reuse it to prove dedup.

## Files touched

- `src/literature_digest/report.py` — replace `build_term_sections` /
  `TermSection` with `build_filterable_articles` + `TermMeta`; update
  `render_area` context.
- `templates/area.html.j2` — remove sidebar/sections; add filter button row,
  flat card list with `data-terms`, flat term pills, filter JS, empty-filter
  placeholder, print CSS updates.
- `tests/test_report.py` — rewrite structure/snapshot tests for the new shape.
- No model / pipeline / CLI / source changes. `matched_terms` already exists
  on `Article` (subtask 05) and is populated correctly by every source.

## Acceptance criteria

- [ ] Each retained article appears **exactly once** in the rendered report —
  card count equals the unique article count, even when an article matches
  multiple terms.
- [ ] A row of filter buttons along the top lists every matched term + "All",
  each showing its unique-article count; the active button is highlighted.
- [ ] Clicking a term button hides every card whose `data-terms` does not
  contain that term; clicking "All" shows every card. The active filter is
  reflected in `location.hash` and survives reload.
- [ ] Each card shows one pill per matched term (no "current / also:"
  distinction); untagged cards show a single `Other` pill.
- [ ] A filter that matches zero cards shows the "No articles match this term"
  placeholder instead of a blank area.
- [ ] Print-to-PDF shows all cards regardless of the active on-screen filter;
  filter buttons are hidden in print.
- [ ] The report remains a single self-contained static HTML file (no external
  build step, no external JS/CSS).
- [ ] `uv run pytest` green, including the rewritten `tests/test_report.py`.
- [ ] `uv run ruff check .` clean.
- [ ] Regenerate the on-disk report via `uv run python scripts/render_preview.py
  --area data_science` and confirm in a browser: no duplicate cards, filter
  buttons work, hash-deep-link works.
