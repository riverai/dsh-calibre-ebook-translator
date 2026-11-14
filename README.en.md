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

**Result**: zero content-token cost (bulk text bypasses model context), zero truncation risk, zero generation-induced hallucination. `write_chunk_from_file` includes built-in read-back verification (`verify_mismatch` flag) that compares stored content against the file after writing. CRLF is normalized to LF, UTF-8 BOM is stripped automatically.

If you prefer not to use MCP, manual mode (paste chunk source text by hand) is also available, but you lose the file pipeline's anti-hallucination guarantees and automatic read/write capability.

## What is this

A custom Agent mode for DeepSeek Harness (dsh 0.2.x): chunked whole-book translation with cross-session persistent glossary and memory capsule, independent review subagent, consistency scanning, and scripted verification. Designed for long-form translation fed by Calibre's chunk-by-chunk segmentation.

## Prerequisites (Calibre + chunking)

1. Install [Calibre](https://calibre-ebook.com/).
2. Install the Ebook Translator plugin for Calibre (search "Ebook Translator" in Calibre's plugin marketplace).
3. Open the book you want to translate in Calibre, click the Ebook Translator plugin's translate button — **you don't need to wait for it to finish translating**. You just need it to segment the book into chunks. A merge length of around **6000 tokens** is recommended (adjustable in the plugin settings).
4. Once chunking is done, you can close the plugin and Calibre — subsequent translation is handled by this workflow through MCP, which reads and writes the cache directly.

## Installation

**Step 1: Install the companion MCP** (follow the instructions at https://github.com/riverai/MCP-for-Calibre-Ebook-Translator), ensuring the server is named `calibre-ebook-trans`.

**Step 2: Install this plugin**

    dsh plugin --profile web add github:riverai/dsh-calibre-ebook-translator

Or install locally:

    dsh plugin --profile web add file:<full path to this directory>

**Step 3**: Restart `dsh web`. The mode selector will show "书籍翻译模式" (Book Translation Mode).

## Script auto-deployment

This plugin package includes a `scripts/` subdirectory with five Python tools:
verify-chunk.py, apply-edits.py, glossary-append.py, scan-consistency.py, export-full.py.

The translation agent automatically copies these scripts from the package install path to the workspace root (the directory containing `books/`) on the first chunk of a new workspace. No manual action needed.

For manual deployment: copy `scripts/*.py` to your workspace root.

## The script toolkit

This plugin is not just a prompt — it ships with a Python tool chain forged by real translation incidents. Each tool corresponds to a problem that actually happened.

### verify-chunk.py — structural/punctuation/format verification (run 3x per chunk)

A mandatory safety net for every chunk, run at three checkpoints: after drafting (`-t draft`), after review edits (`-t review`), and after copying to final (default). 16 checks with **FAIL/WARN tiering**:

- **Structural alignment**: line count, non-empty block count, per-line blank pattern — source line i must be translation line i (the hard invariant for MCP alignment and consistency scanning)
- **En-dash check (tiered)**: source has dash but translation doesn't = **FAIL** (missed punctuation); translation has extra dash = **WARN** (may be legitimate, needs adjudication) — neither blanket-bans nor lets misses through
- **Format hygiene**: no ASCII straight quotes (must be full-width Chinese), no full-width slash, no literal `\n`, **no markdown markers** (`**` bold etc. — triggered 4 chunks in a row in practice), no BOM, no tabs, no trailing spaces
- **Quote checks**: nested quotes must use full-width single quotes `''`, quote direction anomaly detection (`"旅人"` reversed — a real incident)
- **Draft→final changed line count**, **review→final verbatim identity** (guards against accidental edits to the finished product)
- **Assertions**: `-a "must-appear"` / `-x "must-not-appear"`

**WARN does not count toward FAIL and does not change the exit code, but every WARN must be individually adjudicated before proceeding — never ignore or filter it out.** Exceptions can be registered in a `.verify-exceptions` file (format `NNN:L reason`), but only for approved translation conventions (e.g. literary quotations following a standard published translation) — never to mask real errors.

### apply-edits.py — precision batch-edit tool (the only approved edit path)

All batch edits to translations **must** go through this tool; ad-hoc one-off scripts are forbidden. Every design decision corresponds to a real incident:

- **Uniqueness assertion**: each `old_string` must appear exactly once in the target file, or the entire batch rolls back ("FATAL: BATCH ROLLED BACK") — prevents collateral damage
- **Occurrence column (4th, optional)**: three ways to handle repeated strings — empty = strict uniqueness (default); `all` = replace all (**whole-line anchors only** — short-string + `all` is a bug, not a feature); `k` = replace the k-th occurrence
- **Batch-conflict precheck**: two edits in the same batch with identical `old_strings` (or where one is a substring of the other) are rejected — this stems from a real incident: two edits sharing an old_string both passed the uniqueness precheck, but applying them in order made the second a silent no-op (`str.replace` returned the original) while still printing "applied" — a term correction vanished this way and was only found much later by a whole-book scan
- **Quote-glyph trap protection**: ASCII `"` (U+0022) and full-width `""` (U+201C/U+201D) look identical but differ in bytes; hand-typing old_strings will produce the wrong bytes. The script auto-strips BOM and CR, but quote glyphs must be read from the file or constructed by code point
- **`--fix-quotes`**: converts ASCII double quotes to full-width with open/close direction alternation (only touches double quotes, preserves English apostrophes like `Swann's Way`)

Input is a TSV file (`old_string<TAB>new_string<TAB>note<TAB>occurrence`), deleted after use.

### glossary-append.py — glossary maintenance tool

The glossary is not just "a record of translations" — it is the foundation of whole-book consistency. This tool manages its appendage and correction:

- **Four modes**: `append` (add new row), `edit` (modify an existing row's translation, old value auto-moves to 备注 as `勿用:X`), `edit-note` (modify the note column), `add-row` (interactive single-row append)
- **Pipe sanitization**: no half-width `|` may appear inside any cell (it splits the row and the note tail is silently dropped by parsers — one incident lost 15 rows' notes). The script auto-replaces `|` with `／`
- **Parser rejoin**: both parsers (glossary-append.py and scan-consistency.py) split only on unescaped pipes and, when a row has more than 5 columns, rejoin the surplus back into the note — so legacy broken rows cannot silently lose their note tail
- **Note micro-syntax**: `候选:X` (candidate rendering, positional check treats as compliant), `勿用:X` (deprecated rendering, presence is flagged), `订正:DATE ...` (correction record), `源文:...` (source-text defect), free prose (last). Markers use half-width colons, no markdown, no parentheses
- **lint / normalize**: `lint` is a read-only report (checks format issues), `normalize` is format-only repair (no semantic change)

### scan-consistency.py — cross-chunk consistency scanner

The most powerful quality assurance tool in the workflow. It is not a simple "forbidden-word scanner" — the early version degenerated into a checker for a few built-in forbidden words, looked green while real drift accumulated. It has been rewritten with six checks:

**A. Term positional check (the main check)** — reads the entire glossary and, for every occurrence of every source term in the source text, checks the translation's **same line** for the approved rendering or any candidate. Relies on the hard invariant: source line i = translation line i (guaranteed by verify-chunk.py). Reports in two tiers (do not flatten):
- **Tier 1 position drift** (act on these): high-specificity terms (multi-word phrases, proper nouns) that are compliant somewhere and non-compliant elsewhere — this is drift, not mere non-compliance
- **Tier 2 glossary-vs-text disagreement** (reconcile the table): a term whose rendering never matches anywhere — this is a table-vs-text disagreement, not a position bug

**B. Deprecated-rendering residue (勿用)** — deprecated renderings appearing anywhere in the translation. Kept because the positional check has a containment blind spot (when the approved form is "莫", the erroneous "莫乌" also contains "莫" and passes); only the deprecated list catches this class. A and B are complementary, not substitutes.

**C. Reminder words (OFF by default)** — no built-in reminder-word list (deliberately): a generic list degrades the whole scan into "checking a few words", which is worthless. Pass a book-specific list with `--watch-words`. A hit is a hint, never a verdict.

**D. Term discovery (`--discover`)** — finds recurring English phrases in the source that are **not in the glossary**. Drift often exists simply because a term was never in the table, so it was never checked.

**E. Review/final divergence (`--stage both`)**

**F. Candidate/containment conflicts (`--collisions`)** — reports four buckets: A self-contradiction (candidate and deprecated value contain each other — must fix) / B cross-row containment shading (one row's approved form is a substring of another row's rendering — **where drift hides**) / C same-row long-short coexistence (usually fine) / D deprecated superstring of approved form (informational)

**Exit codes**: 0 = clean, 2 = findings to adjudicate, 1 = error. **Tier 2 does not affect the exit code** (it's the reconciliation list); only Tier 1 drift, deprecated residue, review/final divergence, and class-A collisions gate it. `--strict-all` makes Tier 2 gate as well; `--exit-zero` forces 0.

**Four known limitations** (documented, not hidden): (1) containment blind spot — approved rendering is substring of wrong rendering, positional check can't see it (covered by B and `--collisions`); (2) same string, two referents — one glossary row can't distinguish; (3) same word, everyday sense — words that are both a locked term and ordinary vocabulary can't be adjudicated per position (leave in Tier 2); (4) coverage dependence — the scan's ceiling is the glossary's coverage, use `--discover` to break through.

**Exceptions**: `.scan-exceptions` file, three granularities plus a multi-word form (`NNN:L term reason` / `NNN term reason` / `* term reason` / `NNN:L | term with spaces | reason`). Register only adjudicated legitimate deviations, never to silence real errors.

### export-full.py — full-book export

Concatenates all `translations/chunk-NNN.txt` in numeric order into `translations/_full.txt`. Reports retrospective-change summary and pending-adjudication items on export.

## Usage

### Default translation style

If you don't specify a translation style, the workflow uses a built-in default that prioritizes **accuracy**: faithful retention of original content, structure, and punctuation; modern standard written language; no self-inflated literary tone (no adding archaic diction the source doesn't have), but preserving the register the source itself carries; no clichés (meaning exhaustion + semantic drift); technical terms annotated with original English on first occurrence.

To specify a style, state it when opening a new book — user-specified styles take priority over the built-in default and are written to the memory file immediately.

### Starting a translation

Enter:

    开新书 <book-name>  your style preferences, or leave blank to use the built-in style

The workflow creates a glossary, progress log, and memory capsule in markdown.

### Run one test chunk first (the AI proactively recommends this)

The AI will proactively suggest at session start: run one chunk manually to calibrate the workflow, then switch to goal mode. **Following this order is strongly recommended** — run one chunk, observe whether the AI correctly uses the full pipeline (file-pipeline source reading, script verification, review subagent, adjudication on screen, final written to MCP). If the flow is correct, proceed to goal mode for the rest of the book.

### Goal mode (AI-initiated, completes the whole book)

After confirming the first chunk's flow is correct, the AI will proactively ask whether to enter goal mode (you can also manually enter `/goal`). In goal mode:

- Most decisions are made autonomously by the AI (term choices, translation strategy, review fixes, consistency corrections).
- Important questions (whole-book term re-decisions, style pivots, meaning-changing ambiguities) are written to the memory file's `## 待裁定` section — the AI proceeds with its best judgment, and the user adjudicates after the goal run.
- All quality rules (pipeline, memory contract, editing discipline, verification) apply unchanged — goal mode only removes the per-chunk human checkpoint.

### Periodic checks (recommended every ~30 chunks)

The AI may drift from the standard workflow during long tasks. Check every **~30 chunks**:

- Is the AI still following the 14-step pipeline (read memory → fetch source → term scan → draft → verify → review → adjudicate on screen → edit → copy to final → write back to MCP → update glossary → update memory/progress/reports)?
- Are review adjudications still being output item-by-item on the main screen?
- Are scripts still running 3x per chunk (draft / review / final)?

If drift is found, correct it in the conversation — your instructions are written to the memory file and subsequent chunks will follow them.

### Everything you say in the conversation is remembered

Whatever you want to say, do, or adjust — say it in the conversation. It gets written to the memory file and takes priority over the AI's autonomous judgment. For example:

- "Translate this term as X throughout" → written to `## 用户指令`, followed for the rest of the book
- "Make the tone more colloquial" → updates style notes, takes effect immediately
- "I disagree with review item #3" → the AI re-adjudicates

### Memory and glossary

- Before each chunk, the main agent proactively reads three files (memory.md, glossary.md, progress.md) to prevent forgetting over many rounds.
- Every standing instruction you give is recorded in the memory file, closing the loop with earlier design decisions.
- The glossary contains source text, translation, category, first-occurrence chunk, notes and alternates — the same term may have different candidate translations (candidate + deprecated markers).

### Translation flow

- The main agent already has the large context provided by the framework; no extra context ingestion is needed.
- Draft written to temp file → review → precision edit → copy to final → write back to MCP (file pipeline, text bypasses conversation, zero hallucination risk).
- The finished translation is written to a `.txt` file.
- The main screen does not output the full translation, but outputs new term decisions, translation highlights, difficulties, review adjudications, and open issues.
- **All on-screen information is copied verbatim to reports.md** — even if the conversation is compacted, the on-screen history is preserved in the file for future reference.

### Review

- The review subagent is a blank slate — it uses the read tool to read the source chunk, draft, glossary, and the previous 1-2 finished translation chunks.
- The main agent also passes the review subagent extensive details about the current chunk's translation decisions and difficulties.
- After receiving sufficient information, the review subagent returns a structured review; the main agent decides whether to accept or reject each item.
- Review adjudications must be output on the main screen first (seven-column table: # / target (with line number) / source / original translation / review text / verdict / reason) before any edit is applied.
- If a review item suggests a term translation (even if mentioned only once), it must be captured in the glossary — new term gets a row, existing term gets a candidate or triggers a retrospective change.

### Retrospective changes (回改)

- When the main agent discovers an error in a previously finished translation, it uses search and read tools to fix it (may require user authorization).
- Every retrospective change is immediately recorded in the memory file; on final export, all retrospective changes are reprinted on the main screen.
- Retrospective changes trigger a ripple warning: a book is a tightly coupled system — changing one place often means other places need changing too; the scan tool locates affected chunks.

## Done 🎉

When all chunks are translated, all `## 待裁定` items are resolved, and all retrospective changes are landed, the workflow reports the book complete. At this point, return to Calibre, open the Ebook Translator plugin — all translations have been written back to the translation cache via MCP — and click **Export Book**:

- Choose your preferred format (EPUB, PDF, AZW3, etc.)
- Choose bilingual or single-language
- Choose display styles

What you get is your complete translated book. Enjoy.

## License

MIT License — see [LICENSE](LICENSE).
