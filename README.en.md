# dsh-calibre-ebook-translator

English | [中文](README.md)

> Adapting the Calibre Ebook Translator plugin to a modern agent workflow.

This project evolved from a blog prompt (2023 edition) into a full agent workflow, refined through 74 chunks of real book translation. What started as a simple translation prompt is now a complete chunked whole-book translation system.

- **Blog**: https://www.yayaus.com/2025/02/11/calibre%E6%8F%92%E4%BB%B6ebook-translator%E6%8F%92%E4%BB%B6%E7%9A%84%E6%8F%90%E7%A4%BA%E8%AF%8D%E5%88%86%E4%BA%AB.html
- **GitHub**: https://github.com/riverai/dsh-calibre-ebook-translator

The Calibre Ebook Translator plugin has no MCP support, so early versions required manual copy-paste. A feature request was submitted to the Ebook Translator project but has not been adopted. This plugin now reads and writes chunks directly through a companion MCP server — no more manual pasting.

## Companion MCP (required)

This plugin depends on a companion MCP server to read and write the Calibre translation cache directly:

- **MCP project**: https://github.com/riverai/MCP-for-Calibre-Ebook-Translator

You **must** name the MCP server `calibre-ebook-trans` (matching the hardcoded tool prefix `mcp__calibre-ebook-trans__` in the protocol). If you use a different name, all MCP tool calls in the protocol will fail to resolve.

### The MCP file pipeline: anti-hallucination + token savings

This is one of the most important engineering decisions in this workflow. The traditional MCP call pattern is `get_original` (read source into the conversation) → agent translates → `write_chunk` (pass translation string back) — text passes through the model context twice, each time risking truncation, mutation, and hallucination, while consuming large amounts of tokens.

This plugin replaces it with a **file pipeline**:

| Step | Traditional | File pipeline (this plugin) |
|---|---|---|
| Read source | `get_original` → text enters conversation → agent writes to .txt | `get_original_to_file` → MCP exports directly to local .txt, **text never enters conversation** |
| Write translation | agent outputs translation → `write_chunk` with string | `write_chunk_from_file` → pass .txt file path, MCP reads it itself, **text never enters conversation** |
| Export for rework | `get_translation` → text enters conversation | `get_translation_to_file` → export to local .txt, **text never enters conversation** |

**Result**: zero content-token cost (bulk text bypasses model context), zero truncation risk, zero generation-induced hallucination. `write_chunk_from_file` includes built-in read-back verification (`verify_mismatch` flag). CRLF is normalized to LF, UTF-8 BOM is stripped automatically.

If you prefer not to use MCP, manual mode (paste chunk source text by hand) is also available, but you lose the file pipeline's anti-hallucination guarantees and automatic read/write capability.

## What is this

A custom Agent mode for DeepSeek Harness (dsh 0.2.x): chunked whole-book translation with cross-session persistent glossary and memory capsule, independent review subagent, consistency scanning, and scripted verification. Designed for long-form translation fed by Calibre's chunk-by-chunk segmentation.

## Prerequisites (Calibre + chunking)

1. Install [Calibre](https://calibre-ebook.com/).
2. Install the Ebook Translator plugin for Calibre (search "Ebook Translator" in Calibre's plugin marketplace).
3. Open the book you want to translate in Calibre, click the Ebook Translator plugin's translate button — **you don't need to wait for it to finish translating**. You just need it to segment the book into chunks. A merge length of around **6000 tokens** is recommended.
4. Once chunking is done, you can close the plugin and Calibre — subsequent translation is handled by this workflow through MCP.

## Installation

**Step 1: Install the companion MCP** (follow the instructions at https://github.com/riverai/MCP-for-Calibre-Ebook-Translator), ensuring the server is named `calibre-ebook-trans`.

**Step 2: Install this plugin**

    dsh plugin --profile web add github:riverai/dsh-calibre-ebook-translator

Or install locally:

    dsh plugin --profile web add file:<full path to this directory>

**Step 3**: Restart `dsh web`. The mode selector will show "书籍翻译模式" (Book Translation Mode).

## Script auto-deployment

This plugin package includes a `scripts/` subdirectory with five Python tools: verify-chunk.py, apply-edits.py, glossary-append.py, scan-consistency.py, export-full.py. The translation agent automatically copies these to the workspace root on the first chunk. No manual action needed.

## The script toolkit

This plugin is not just a prompt — it ships with a Python tool chain forged by real translation incidents.

### verify-chunk.py — structural/punctuation/format verification (run 3x per chunk)

Mandatory safety net for every chunk, run at three checkpoints: after drafting (`-t draft`), after review edits (`-t review`), and after copying to final (default). 16 checks with **FAIL/WARN tiering**: structural alignment (line count, block count, blank pattern), en-dash check (source has dash but translation doesn't = FAIL; extra dash = WARN), format hygiene (no ASCII quotes, no markdown, no BOM, no tabs), quote nesting/direction checks, draft→final identity, assertions. WARN must be individually adjudicated — never ignored.

### apply-edits.py — precision batch-edit tool (the only approved edit path)

All batch edits **must** go through this tool. Uniqueness assertion (exactly once or batch rollback), occurrence column (empty/all/k), batch-conflict precheck (two edits sharing old_string rejected — stems from a real silent-no-op incident), quote-glyph trap protection, `--fix-quotes`, and retroactive dual-write (same TSV to both translations/ and .review.txt).

### glossary-append.py — glossary maintenance tool

Six subcommands: append, edit, edit-note, add-row, lint, normalize. Pipe sanitization (| → ／), parser rejoin (>5 columns rejoined back into notes), note micro-syntax (候选/勿用/订正/源文), structural-vs-style error separation in lint.

### scan-consistency.py — cross-chunk consistency scanner (v1.2 major upgrade: 13 checks)

**The most powerful quality assurance tool in the workflow, and the core of the v1.2 upgrade.**

The early version had only six checks (A-F), all glossary-dependent — meaning **anything the glossary didn't cover was completely invisible**. A chapter heading never registered as a term, a set of numbers never entered into the table, an entire reference list left untranslated — A-F were structurally blind to all of these. In practice: one book had 6 repeated-line divergences, a 24-line reference list entirely untranslated, 16 URLs and 9 DOIs lost — A-F caught none of them.

v1.2 adds seven **glossary-independent** checks (G-M) that compare source and translation directly, breaking through the coverage ceiling:

| Check | Needs glossary? | What it catches | Measured value |
|---|---|---|---|
| **A. Term positional** | Yes | Every term's rendering at every occurrence (two tiers: drift vs disagreement) | 2371 terms / 4414 positions |
| **B. Deprecated residue** | Yes | Deprecated renderings anywhere | Fills A's containment blind spot |
| **C. Reminder words** | No (optional) | Book-specific watch list (OFF by default) | Hint, not verdict |
| **D. Term discovery** | Yes | Recurring source phrases NOT in glossary | Breaks coverage blind spot |
| **E. Review/final divergence** | Yes | Review file and final must be byte-identical | Guards pipeline integrity |
| **F. Candidate/containment conflicts** | Yes | Candidate vs deprecated containment (four buckets) | B is where drift hides |
| **G. Repeated-line consistency** ⭐ | No | Identical source lines must be translated identically | 6 divergences in one book, invisible to A-F |
| **H. Heading-normalized** ⭐ | No | Strip chapter prefixes, compare heading cores | Closes G's blind spot |
| **I. Untranslated residue** ⭐ | No | Whole-line English prose with no CJK / inline ≥8 English words | 24-line reference list untranslated |
| **J. Number consistency** ⭐ | No | Numbers (incl. Chinese numeral spellings) must survive | 73→0 (handles 二十世纪/三十六亿/十二万六千 etc.) |
| **K. Identifier retention** ⭐ | No | URLs/DOIs/ISBNs/citation years must survive | 16 URLs + 9 DOIs lost |
| **L. Cross-reference consistency** ⭐ | No | "see Chapter 12" → 第12章 or 第十二章 accepted | 5 books L=0 |
| **M. Per-line volume anomaly** ⭐ | No | Extreme length ratio (compression<0.08 / expansion>2.5) | False positives 179→0-2 |

⭐ = new in v1.2, glossary-independent, **immune to the coverage ceiling**.

**A-F in detail (glossary-dependent checks)**:

- **A. Term positional check** — reads the WHOLE glossary and, for every occurrence of every source term in the source, checks the SAME LINE of the translation for the approved rendering or any candidate. Relies on the hard invariant: source line i = translation line i (guaranteed by verify-chunk.py). Reports in TWO TIERS (do not flatten): Tier 1 position drift (act: high-specificity terms compliant somewhere but non-compliant elsewhere — inconsistency, not non-compliance); Tier 2 glossary-vs-text disagreement (reconcile the table: a term whose rendering never matches anywhere).
- **B. Deprecated-rendering residue** — deprecated renderings anywhere in the translation. The positional check has a containment blind spot (when the approved form is a substring of a wrong rendering, the wrong one also contains the approved and passes); only the deprecated list catches that class. A and B are complementary, never substitutes.
- **C. Reminder words (OFF by default)** — no built-in list, deliberately: a generic list degrades the whole scan into "checking a few words". Pass a book-specific list with --watch-words. A hit is a HINT, never a verdict.
- **D. Term discovery (--discover)** — recurring English phrases NOT in the glossary. Drift often exists because a term was never in the table.
- **E. Review/final divergence (--stage both)** — review file and finished product must be byte-identical; divergence means the pipeline was broken.
- **F. Candidate/containment conflicts (--collisions)** — four buckets: A self-contradiction (must fix); B cross-row containment shading (**where drift hides**); C same-row coexistence (usually fine); D deprecated superstring (informational).

**G-M in detail (glossary-independent, new in v1.2)**:

- **G. Repeated-line consistency** — a source line that is EXACTLY identical wherever it appears must be translated identically. Covers what A-F are structurally blind to: contents entries vs real chapter headings, repeated column names, running heads/feet. SCOPE WARNING: G only sees byte-identical lines; a contents line "Chapter 22: X" and body heading "X" are NOT the same line — that needs H.
- **H. Heading-normalized comparison** — closes G's blind spot. Both sides have structural prefixes stripped (Chapter N: / Part X: / 1) / 100. / roman numerals / 第N章：), then translated cores are compared. G and H are complementary and do not double-report.
- **I. Untranslated residue** — whole-line: source is English prose (≥3 lowercase words, length ≥40, minus URLs) and translation has NO CJK character. In-line: ≥8 consecutive English words. Using "lowercase words" lets Title Case company names drop out automatically. Measured: a 24-line reference list left entirely in English.
- **J. Number consistency** — the CRITICAL measured fact: Chinese translations write numbers in Chinese numerals a great deal (1970s→二十世纪七八十年代, 3.6 billion→三十六亿, 126,000→十二万六千). J expands each number into all legitimate spellings before comparing. Measured iteration: 73→0.
- **K. Identifier retention** — URLs, DOIs, ISBNs, citation years, postcodes must appear in the translation, verbatim or by value. ISBN compares DIGITS ONLY. Measured: 16 URLs + 9 DOIs lost in one book.
- **L. Cross-reference consistency** — "see Chapter 12" must yield 第12章 OR 第十二章 — BOTH accepted. Page references and Kindle locations only require the number to survive.
- **M. Per-line volume anomaly** — the WEAKEST check: measured p5≈0.26, median 0.31-0.41, p95≈0.58-1.04 across five books. Only ABSOLUTE extreme thresholds: compression <0.08, expansion >2.5. The script prints the book's own distribution for human judgment.

**Exit codes**: 0 = clean, 2 = findings to adjudicate, 1 = error. Tier 2 does NOT affect the exit code. What gates it: Tier 1 drift, deprecated residue, review/final divergence, class-A collisions, repeated-line divergence, heading divergence, untranslated residue, missing identifiers, number mismatch, broken cross-references, volume outliers. --strict-all makes Tier 2 gate; --exit-zero forces 0.

**Exceptions**: `.scan-exceptions` file, three granularities plus a pipe form: `NNN:L 原文 理由` / `NNN 原文 理由` / `* 原文 理由` / `NNN:L | 原文含空格时 | 理由`. Apply to A/B/E and G-M alike. Register ONLY adjudicated legitimate deviations. Do NOT register a book-wide exception for an everyday-sense word — leave it in Tier 2.

**`--quick` mode**: runs only G-M (seconds), can run **after every chunk** — drift is caught at the chunk where it happens, not accumulated to the next 10-chunk cycle.

**Core discipline — never loosen the matcher**: when a check produces false positives, the correct response is to **keep the matcher strict and register an explicit exception**. Relaxing the rule (adding candidates, accepting composites) buys quiet at the price of PERMANENT BLINDNESS — a missed drift never announces itself. This has happened twice in this project already.

### export-full.py — full-book export

Concatenates all `translations/chunk-NNN.txt` into `translations/_full.txt`. Reports retrospective-change summary and pending-adjudication items.

## Usage

### Default translation style

If you don't specify a style, the workflow uses a built-in default prioritizing **accuracy**: faithful retention of content, structure, punctuation; modern standard written language; no self-inflated literary tone but preserving the source's own register; no clichés (meaning exhaustion + semantic drift); technical terms annotated with original English on first occurrence. User-specified styles take priority and are written to memory immediately.

### Starting a translation

    开新书 <book-name>  your style preferences, or leave blank for built-in defaults

### Run one test chunk first (the AI proactively recommends this)

The AI will suggest at session start: run one chunk manually to calibrate, then switch to goal mode. Observe whether the AI correctly uses the full pipeline. If correct, proceed to goal mode.

### Goal mode (AI-initiated)

The AI will proactively ask whether to enter goal mode (or manually `/goal`). Most decisions are autonomous; important questions go to `## 待裁定` for post-run adjudication. All quality rules apply unchanged.

### Periodic checks (every ~30 chunks)

Check whether the AI is still following the 14-step pipeline, outputting adjudications on screen, and running scripts 3x per chunk. Correct drift in the conversation — instructions are written to memory.

### Everything you say is remembered

Instructions in the conversation are written to the memory file and take priority over the AI's autonomous judgment.

### Memory, glossary, translation flow, review, retrospective changes

- The agent reads memory.md, glossary.md, progress.md before each chunk.
- Draft → review → precision edit → copy to final → write back to MCP (file pipeline, zero hallucination).
- On-screen output (term decisions, highlights, difficulties, adjudications, open issues) is copied verbatim to reports.md.
- Review subagent reads the draft (never the final), gets file paths + style notes + checklist, returns numbered issues; adjudication is a seven-column table output before any edit.
- Retrospective changes (回改) are recorded in memory; ripple warning scans for affected chunks.

## Done 🎉

When all chunks are translated, all `## 待裁定` resolved, and all retrospective changes landed, return to Calibre's Ebook Translator plugin and click **Export Book**. Choose format (EPUB/PDF/AZW3), bilingual or single-language, display styles. Enjoy your book.

## License

MIT License — see [LICENSE](LICENSE).
