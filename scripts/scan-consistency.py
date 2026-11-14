#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scan-consistency.py — 跨块一致性扫描器（v2.1）

════════════════════════════════════════════════════════════════════════
设计原则（读这一节比读代码重要）
════════════════════════════════════════════════════════════════════════

【原则 1】术语漂移只能用"位置对位"问责，不能用"词表黑名单"排查。

  本项目有一条硬不变量：**源文行 ↔ 译文行 一一对应**。它由 verify-chunk.py
  强制保证（行数一致 ＋ 逐行空行模式一致 ＋ 非空块数一致）。因此可以做到：

      源文 chunk-NNN 第 L 行发现术语 X
        → 检查译文 chunk-NNN 第 L 行
        → 是否出现 X 的【规范译法】或任一【候选译法】？
        → 都没有 = 该位置不合口径

  v1 只能发现"已被抓过一次并记进旧译栏"的错误，对新漂移完全无感；v2 按位置问责。

【原则 2】"漂移"的本质是【不一致】，所以判定要分两层。

  朴素做法（"该行没出现规范译法就报漂移"）会淹死在噪音里：同一个英文词往往
  既是锁定术语、又是日常词（success / time / face / work / band …），
  而且术语表的一格常是"暂拟写法"，正文后来换了别的说法。所以：

    · 第一层（Tier 1｜位置漂移，须裁定）
        只对【高辨识度】术语启用逐位置问责：多词短语、含大写的专名/类别名、
        或罕用长词。且必须满足"**同一术语有位置合规、有位置不合规**"——
        这才是货真价实的不一致。全合规或全不合规都不进这层。

    · 第二层（Tier 2｜术语表口径与正文不符，供人工核对）
        其余情况按【术语】汇总一行（不再逐位置刷屏）：说明该术语在源文出现
        N 次，而译文从头到尾没有采用表里的写法。这通常是两种情况之一：
          (a) 术语表那一格写的是暂拟译法，正文后来统一成了另一个说法；
          (b) 正文确实全程偏离口径（系统性漂移）。
        两种都该由人来定：改表，或改正文。

  这样 Tier 1 短而准（该动手的地方），Tier 2 短而全（该对表的地方）。

【原则 3】日/英常见词、专名大小写、复数、书名级变体，都要专门处理。
  见下方 build_src_regex / accept_spec / 覆盖豁免(waiver) 的注释。

【原则 4】提醒词不是"禁词"，默认【不启用】。
  每本书语感不同，一份通用提醒词表只会把整套扫描退化成"少数几个词的检查"。
  默认表已移除（保留为下方注释示例）。要用就 --watch-words 传该书专属表。

【原则 5】只产出漂移报告，绝不自动改文件。是否回改由人或 agent 裁定。

════════════════════════════════════════════════════════════════════════
检查项
════════════════════════════════════════════════════════════════════════
  A. 术语对位（Tier 1 位置漂移 ＋ Tier 2 表与正文不符）
  B. 勿用残留（辅助）  备注里"勿用:X"出现在译文任意位置 → 报告
        保留 B 的理由：A 的判定是"译文行是否包含规范译法"，而"包含"有天然
        盲区——规范译法是「莫」时，错误写法「莫乌」也包含「莫」，A 判为合规。
        B 正好补这个洞。A+B 互补，不可互相替代。
  C. 提醒词（可选，默认关闭）
  D. 术语发现（--discover）：找复现高但术语表没有的英文短语（治本——漂移的
     根因往往是"这个术语压根没入表，所以从来没被检查过"）
  E. 审校稿/成品分歧（--stage both）
  F. 候选/包含关系冲突（--collisions；常规运行顺带报 A 类）
       对位判定靠"译文行是否**包含**规范译法"，所以当【规范译法是某个错误写法
       或被另一条规则认定为合规的写法的子串】时，对位检查**必然失效**：
           规范「鹈鹕」 vs 实际「鹈鹕图书」 → 含「鹈鹕」 → 判合规（真事）
           规范「莫」   vs 实际「莫乌」     → 含「莫」  → 判合规（真事）
       机器判不了这类，只能把可疑组合列给人看。四桶：
         A｜自相矛盾（必须修）：同一行的【候选】与【勿用】互相包含
              —— 等于同时宣布"可以这么写"与"不可以这么写"，是登记失误。
              （注意：规范⊂候选 是正当的"长短并存"；规范⊂勿用 是有意的弃用，
                两者都不是矛盾，故不计入 A。）
         B｜跨行包含遮蔽（须复核）：短译法是另一术语行的更长译法的子串。
         C｜同行长短并存（提示·通常正当）
         D｜勿用超串警示（提示）：勿用值是规范译法的超串（勿用检查会命中
              规范译法内部，如「电讯报」⊂《每日电讯报》）；本脚本已内置子串过滤。

════════════════════════════════════════════════════════════════════════
例外登记：books/<slug>/.scan-exceptions
════════════════════════════════════════════════════════════════════════
      NNN:L  原文   理由      # 只豁免该块该行的该术语
      NNN    原文   理由      # 豁免该块内该术语的所有位置
      *      原文   理由      # 全书豁免该术语

  # 开头为注释。示例：
      037 dominance 此处 dominance hierarchy=支配等级，非支配型游戏

════════════════════════════════════════════════════════════════════════
用法
════════════════════════════════════════════════════════════════════════
  python scan-consistency.py -s statusgame                    # 全书体检
  python scan-consistency.py -s statusgame --stage both        # 含审校稿/成品分歧
  python scan-consistency.py -s statusgame --term dominance    # 单术语追踪
  python scan-consistency.py -s statusgame --tier1 virtuosi    # 把某词提到一层
  python scan-consistency.py -s statusgame --format detail     # 看上下文
  python scan-consistency.py -s statusgame --watch-words w.tsv # 附加提醒词
  python scan-consistency.py -s statusgame --discover          # 术语发现

退出码：0 = 通过；2 = 有 Tier 1 漂移或勿用残留（--exit-zero 强制 0）；
        1 = 参数/文件错误。Tier 2 不计入退出码，但会在报告中出现。
"""

import argparse
import bisect
import json
import re
import sys
from pathlib import Path

# ────────────────────────────────────────────────────────────────────────
# 提醒词示例（【默认不启用】）
#
# v1 曾把这张表硬编码为"通用提醒词"，已按原则 4 停用，仅留作写法示例。
# 想用就复制一份到 books/<slug>/_watch.tsv（每行一个词）并 --watch-words 传入。
# 切记：这是【提示】，不是【禁词】；命中不等于错误，只等于"请看一眼"。
#
#   "栖居", "栖身", "身居", "毋宁说", "诸般", "怒不可遏", "势能",
#   "掠食者", "对立人物", "脑壳", "快感", "幸福繁荣", "茁壮成长",
#
DEFAULT_WATCH_WORDS: list = []

CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
LATIN_RE = re.compile(r"[A-Za-z]")
SEP_RE = re.compile(r"[\s\u2010-\u2015\-]+")            # 空白 / 各种连字符
BOOKMARK_TRIM = "《》〈〉「」『』“”\"'‘’ \t"

# 术语发现模式用 + 常用词判定用：高频英文功能/日常词
COMMON_WORDS = {
    "the", "and", "of", "to", "in", "a", "an", "that", "is", "was", "were", "for",
    "on", "with", "as", "at", "by", "or", "be", "been", "are", "it", "its", "this",
    "these", "those", "from", "but", "not", "no", "we", "our", "us", "they", "their",
    "them", "he", "she", "his", "her", "him", "you", "your", "i", "my", "me", "who",
    "whom", "which", "what", "when", "where", "why", "how", "than", "then", "there",
    "here", "so", "such", "if", "into", "out", "up", "down", "over", "under", "again",
    "more", "most", "much", "many", "some", "any", "all", "each", "every", "both",
    "few", "other", "others", "same", "only", "own", "also", "too", "very", "can",
    "could", "would", "should", "may", "might", "must", "will", "shall", "do", "does",
    "did", "done", "have", "has", "had", "having", "get", "got", "make", "made",
    "like", "just", "even", "still", "yet", "about", "because", "while", "after",
    "before", "between", "during", "through", "against", "upon", "within", "without",
    "one", "two", "three", "first", "second", "third", "new", "old", "good", "bad",
    "big", "small", "long", "short", "high", "low", "see", "seen", "say", "said",
    "says", "know", "known", "think", "thought", "come", "came", "go", "went", "take",
    "took", "give", "gave", "find", "found", "tell", "told", "use", "used", "using",
    "way", "ways", "thing", "things", "time", "times", "people", "person", "man",
    "men", "woman", "women", "children", "child", "life", "world", "part", "place",
    "group", "groups", "state", "states", "case", "cases", "fact", "facts", "point",
    "end", "back", "well", "now", "face", "work", "works", "band", "bands", "war",
    "war", "body", "mind", "hand", "head", "home", "house", "name", "side", "line",
    "chapter", "note", "notes", "page", "pages", "ibid", "kindle", "location",
    "university", "press", "journal", "review", "vol", "pp", "ed", "eds", "edn",
    "per", "cent", "course", "coming", "company", "part", "kind", "sort",
    "january", "february", "march", "april", "may", "june", "july", "august",
    "september", "october", "november", "december",
}


# ────────────────────────────────────────────────────────────────────────
# glossary.md 解析
# ────────────────────────────────────────────────────────────────────────

def _glossary_rows(glossary_path: Path):
    """逐行产出 (原文, 译文, 类别, 首现块, 备注)。

    解析要点（都来自真实事故）：
      · 只按**未转义**的竖线切分——Markdown 里 `\\|` 是单元内的字面竖线，不是列分隔符。
        早期用 split("|") 会把合法行误判成列数异常。
      · 若某行被误插入的竖线撑到 5 列以上，**把余下的重新拼回备注**，
        而不是取前 5 列了事——后者会静默丢掉备注尾部（候选/勿用信息可能就在里面）。
    """
    if not glossary_path.is_file():
        return
    for raw in glossary_path.read_text(encoding="utf-8-sig").splitlines():
        if not raw.startswith("|"):
            continue
        if set(raw.strip()) <= set("|-: "):
            continue
        parts = [c.replace("\\|", "|").strip() for c in re.split(r"(?<!\\)\|", raw)]
        if parts and parts[0] == "":
            parts = parts[1:]
        if parts and parts[-1] == "":
            parts = parts[:-1]
        if len(parts) < 5:
            continue
        original, approved, category, first = parts[0], parts[1], parts[2], parts[3]
        note = "；".join(p for p in parts[4:] if p)   # >5 列：余下拼回备注
        if not original or not approved:
            continue
        if original in ("原文",) or set(original) <= set("-: "):
            continue
        if approved == "译文":
            continue
        yield original, approved, category, first, note


def parse_candidates(note: str) -> list:
    """从备注提取"候选:X（理由）/候选:X、Y"中的可选译法（触发其一即合法）。"""
    out = []
    for m in re.finditer(r"候选[:：]\s*([^；;|]+)", note):
        chunk = re.sub(r"[（(][^）)]*[）)]", "", m.group(1))
        if "→" in chunk:
            chunk = chunk.split("→")[-1]
        for piece in re.split(r"[、／/]", chunk):
            piece = piece.strip()
            if piece and piece not in out:
                out.append(piece)
    return out


def parse_forbidden(note: str, approved: str) -> list:
    """从备注提取"勿用:X"（兼容 勿用:X（理由） / 勿用:X→Y）。"""
    out = []
    for m in re.finditer(r"勿用[:：]\s*([^；;|]+)", note):
        val = re.sub(r"[（(][^）)]*[）)]", "", m.group(1))
        if "→" in val:
            val = val.split("→")[0]
        val = val.strip(BOOKMARK_TRIM).split("，")[0].split(",")[0].strip()
        if val and val != approved and val != "—" and val not in out:
            out.append(val)
    return out


class Term:
    __slots__ = ("original", "approved", "category", "first", "note",
                 "candidates", "forbidden", "simple", "composite",
                 "regex", "needle", "specific", "case_sensitive")

    def __init__(self, original, approved, category, first, note):
        self.original = original
        self.approved = approved
        self.category = category
        self.first = first
        self.note = note
        self.candidates = parse_candidates(note)
        self.forbidden = parse_forbidden(note, approved)
        self.simple, self.composite = accept_spec(approved, self.candidates)
        self.regex = build_src_regex(original)
        self.needle = quick_needle(original)
        self.case_sensitive = any(c.isupper() for c in original)
        self.specific = is_specific(original)


def parse_glossary(glossary_path: Path) -> list:
    return [Term(*r) for r in _glossary_rows(glossary_path)]


# ────────────────────────────────────────────────────────────────────────
# 译法归一化：规范译法 + 候选译法 → 可接受的字面集合
# ────────────────────────────────────────────────────────────────────────

def strip_bookmarks(s: str) -> str:
    return s.strip().strip(BOOKMARK_TRIM).strip()


def strip_parens(s: str) -> str:
    s = re.sub(r"（[^）]*）", "", s)
    s = re.sub(r"\([^)]*\)", "", s)
    return s.strip()


def latin_runs(s: str) -> list:
    return re.findall(r"[A-Za-z][A-Za-z0-9.\-’']*(?:\s+[A-Za-z][A-Za-z0-9.\-’']*)*", s)


def split_alternatives(cell: str) -> list:
    for sep in (" 或 ", "或者"):
        if sep in cell:
            cell = cell.split(sep)[0]
    return [p.strip() for p in re.split(r"[；;／]", cell) if p.strip()]


def accept_spec(approved: str, candidates: list):
    """把术语表一行折算成"译文行只要满足其中之一即算合规"的规格。

    返回 (simple, composite)：
      simple    —— 字面集合，出现任意一个即合规
      composite —— 字面组，每组内所有片段都出现才合规（处理带逗号的标题格）

    规则（有意保守：宁可漏判"合规"，也不误放"漂移"）：
      · 取整格字面，去掉《》「」这类书名/引号包装；
      · 若整格形如「中文（Latin）」，额外接受其中的中文部分；
        —— 但**不接受括号里的 Latin**。否则 Republic of Letters 整格是
           「文人共和国（Respublica Literaria）」时，译文行只要还留着
           Respublica Literaria 就算合规，而真正该出现的中文却没出现。
      · 只有当整格是"中文＋Latin 混排"（如「Vice 杂志」）时，才把其中的
        Latin 词串也算作可接受写法（该行本来就打算保留原文）。
      · 整格含逗号（如「公平，不公平」）时，额外登记为 composite：
        各段都出现即可，顺序不限、连接词不限（"公平与不公平" 也合规）。
    """
    simple, composite = set(), []

    def add_cell(cell: str):
        cell = cell.strip()
        if not cell:
            return
        for alt in split_alternatives(cell):
            bm = strip_bookmarks(alt)
            if not bm:
                continue
            simple.add(bm)
            nop = strip_parens(bm)
            if nop and nop != bm:
                simple.add(nop)
            base = nop or bm
            if LATIN_RE.search(base) and CJK_RE.search(base):
                for run in latin_runs(base):
                    if len(run) >= 2:
                        simple.add(run)
            # 族名词尾"人"：表格常写「因纽特人」，正文却用「因纽特」作定语
            # （"一个因纽特家庭"）。故对「X人」额外接受其词干「X」。
            if len(bm) >= 3 and bm.endswith("人"):
                simple.add(bm[:-1])
            parts = [p.strip() for p in re.split(r"[，,]", bm) if p.strip()]
            if len(parts) > 1:
                composite.append(tuple(parts))

    add_cell(approved)
    for c in candidates:
        add_cell(c)
    return simple, composite


def satisfied(line: str, term: Term) -> bool:
    low = line.lower()
    if any(f.lower() in low for f in term.simple):
        return True
    for parts in term.composite:
        if all(p.lower() in low for p in parts):
            return True
    return False


# ────────────────────────────────────────────────────────────────────────
# 源文检索
# ────────────────────────────────────────────────────────────────────────

def plural_suffix(last_word: str) -> str:
    w = last_word.lower()
    if w.endswith(("s", "x", "z", "ch", "sh")):
        return r"(?:es)?"
    if w.endswith("y"):
        return r"(?:ies|s)?"
    return r"(?:s)?"


def build_src_regex(term: str):
    """把术语原文编成正则。

    · 纯 Latin：
        词边界        → war 不命中 warning，age 不命中 agenda
        复数容错      → status→statuses，game→games（"wares" 这类误配已排除）
        连字符容错    → rank and yank 命中 rank-and-yank
      【大小写】若原文含大写字母（专名/类别名），一律【大小写敏感】匹配，
        并【不再容错复数】——否则 "Time"（《时代》杂志）会命中 "time"、
        "Sunday Times"，这是 v2.0 最大的噪音源。
    · 含 CJK：按字面匹配。
    """
    t = term.strip()
    if not t:
        return None
    if LATIN_RE.search(t) and not CJK_RE.search(t):
        words = [p for p in SEP_RE.split(t) if p]
        if not words:
            return None
        pat = SEP_RE.pattern.join(re.escape(w) for w in words)
        case_sensitive = any(c.isupper() for c in t)
        sfx = "" if case_sensitive else plural_suffix(words[-1])
        tail = r"(?:[\u2019']s|" + sfx + r")?" if sfx else r"(?:[\u2019']s)?"
        flags = 0 if case_sensitive else re.IGNORECASE
        return re.compile(r"(?<![A-Za-z0-9])" + pat + tail + r"(?![A-Za-z0-9])", flags)
    return re.compile(re.escape(t))


def quick_needle(term: str) -> str:
    """廉价预筛：用术语首个词做子串判断，避免对全库跑 874×142 次正则。"""
    words = [p for p in SEP_RE.split(term.strip()) if p]
    return (words[0] if words else term).lower()


def is_specific(original: str) -> bool:
    """是否属于"高辨识度"术语（有资格进入 Tier 1 逐位置问责）。

    高辨识度 = 多词短语 ／ 含大写的专名或类别名 ／ 罕用长词（如 virtuosi）。
    单字日常词（success/time/face/work/band/coalition…）一律不逐位置问责——
    它们既是锁定术语又是日常词，逐位置问责只会制造噪音。
    """
    t = original.strip()
    if not t:
        return False
    if re.search(r"[\s\u2010-\u2015\-]", t):
        return True
    if any(c.isupper() for c in t):
        return True
    if t.lower() in COMMON_WORDS:
        return False
    return len(t) >= 7


class LineIndex:
    __slots__ = ("starts",)

    def __init__(self, text: str):
        self.starts = [0]
        for i, ch in enumerate(text):
            if ch == "\n":
                self.starts.append(i + 1)

    def line(self, offset: int) -> int:
        return bisect.bisect_right(self.starts, offset)


# ────────────────────────────────────────────────────────────────────────
# 例外登记
# ────────────────────────────────────────────────────────────────────────

class Exceptions:
    def __init__(self, path: Path):
        self.by_line, self.by_chunk, self.by_book = set(), set(), set()
        self.count = 0
        if not path.is_file():
            return
        for raw in path.read_text(encoding="utf-8-sig").splitlines():
            s = raw.strip()
            if not s or s.startswith("#"):
                continue
            if "|" in s:
                # 竖线分隔写法，用于「原文含空格」的术语：
                #   NNN:L | Ti and Do | 理由
                fields = [f.strip() for f in s.split("|")]
                if len(fields) < 2 or not fields[0] or not fields[1]:
                    continue
                spec, original = fields[0], fields[1].lower()
            else:
                # 空白分隔写法（兼容 .verify-exceptions 习惯）：
                #   NNN:L 原文 理由   —— 此时"原文"不能含空格
                tokens = s.split(None, 2)
                if len(tokens) < 2:
                    continue
                spec, original = tokens[0], tokens[1].lower()
            self.count += 1
            if spec == "*":
                self.by_book.add(original)
            elif ":" in spec:
                try:
                    ch, ln = spec.split(":", 1)
                    self.by_line.add((int(ch), int(ln), original))
                except ValueError:
                    pass
            else:
                try:
                    self.by_chunk.add((int(spec), original))
                except ValueError:
                    pass

    def covers(self, chunk: int, line: int, original: str) -> bool:
        o = original.lower()
        return (o in self.by_book or (chunk, o) in self.by_chunk
                or (chunk, line, o) in self.by_line)


def load_watch_words(tsv_path: Path) -> list:
    if not tsv_path.is_file():
        return []
    return [l.strip() for l in tsv_path.read_text(encoding="utf-8-sig").splitlines()
            if l.strip() and not l.strip().startswith("#")]


def load_term_pairs(json_path: Path):
    if not json_path.is_file():
        return {}
    return json.loads(json_path.read_text(encoding="utf-8-sig"))


# ────────────────────────────────────────────────────────────────────────
# 主扫描
# ────────────────────────────────────────────────────────────────────────

def resolve_stage(book_dir: Path, stage: str):
    if stage == "review":
        return book_dir / "temptranslations", "chunk-%03d.review.txt"
    return book_dir / "translations", "chunk-%03d.txt"


def scan(book_dir: Path, terms: list, chunk_nums: list, stage: str,
         watch_words: list, extra_pairs: dict, exc: Exceptions,
         want_glossary: bool, want_forbidden: bool, want_watch: bool,
         promote: set):
    trans_dir, tmpl = resolve_stage(book_dir, stage)
    src_dir = book_dir / "chunks"

    tier1 = []
    tier2_agg = {}          # 原文 → 全书汇总（Tier 2 必须跨块聚合，不能按块刷屏）
    forbidden_hits, watch_hits = [], []
    parity_bad, missing = [], []
    stats = {"positions": 0, "terms_present": 0}

    for t in terms:
        if t.original.lower() in promote:
            t.specific = True

    for n in chunk_nums:
        src_file = src_dir / ("chunk-%03d.txt" % n)
        dst_file = trans_dir / (tmpl % n)
        if not src_file.is_file() or not dst_file.is_file():
            missing.append(n)
            continue

        # 用 splitlines()：与 verify-chunk / Get-Content 的口径一致。
        # （v2.0 误用 split("\n")，把尾部换行算成一行，导致大量块被误判为
        #   "对位不可靠"而跳过检查。）
        src_lines = src_file.read_text(encoding="utf-8-sig").splitlines()
        dst_lines = dst_file.read_text(encoding="utf-8-sig").splitlines()

        # ── 对位前提守卫（原则 1 的地基） ──
        ok = (len(src_lines) == len(dst_lines) and
              [bool(l.strip()) for l in src_lines] == [bool(l.strip()) for l in dst_lines])
        if not ok:
            parity_bad.append((n, len(src_lines), len(dst_lines)))
            continue                      # 对位前提不成立 → 跳过逐位置问责

        src_text = "\n".join(src_lines)
        src_lower = src_text.lower()
        src_idx = LineIndex(src_text)

        if want_glossary:
            per_term = []                 # [(term, [(L, waived, matched_span)])]
            all_matches = []              # [(term, start, end)]
            for t in terms:
                if not t.regex or not t.simple:
                    continue
                if t.needle not in src_lower:
                    continue
                ms = [(m.start(), m.end()) for m in t.regex.finditer(src_text)]
                if not ms:
                    continue
                stats["terms_present"] += 1
                all_matches.extend((t, s, e) for s, e in ms)
                per_term.append((t, [(src_idx.line(s), s, e) for s, e in ms]))

            # ── 覆盖豁免(waiver) ──
            # 若某处同时命中"短术语"和"更长术语"（success 与 success game），
            # 则短术语在该位置【不再问责】——更长的术语已经替它把口径定死了。
            # 这样 "success games" 只需满足 success game→能力型游戏，
            # 不会被裸词 Success 再判一次。
            for t, occ in per_term:
                tlow = t.original.lower()
                for i, (L, s, e) in enumerate(occ):
                    for t2, s2, e2 in all_matches:
                        if t2 is t or len(t2.original) <= len(t.original):
                            continue
                        if tlow not in t2.original.lower():
                            continue
                        if s < e2 and s2 < e:
                            occ[i] = (L, s, e, True)
                            break

            for t, occ in per_term:
                unmet_pos, met, seen_lines = 0, 0, set()
                unmet_rows = []
                for item in occ:
                    L = item[0]
                    waived = len(item) > 3 and item[3]
                    stats["positions"] += 1
                    line_txt = dst_lines[L - 1] if L - 1 < len(dst_lines) else ""
                    if waived or satisfied(line_txt, t) or exc.covers(n, L, t.original):
                        met += 1
                        continue
                    unmet_pos += 1
                    if L in seen_lines:
                        continue          # 同一行命中多次只报一次（去重）
                    seen_lines.add(L)
                    unmet_rows.append({
                        "chunk": n, "line": L, "original": t.original,
                        "approved": t.approved, "category": t.category,
                        "candidates": t.candidates,
                        "target": line_txt.strip(),
                        "src": src_lines[L - 1].strip() if L - 1 < len(src_lines) else "",
                    })
                if unmet_pos == 0:
                    continue
                if t.specific and met > 0:
                    # Tier 1：同一术语有位置合规、有位置不合规 = 真不一致
                    tier1.extend(unmet_rows)
                else:
                    # Tier 2：按术语【全书】聚合一行（不再按块刷屏）
                    agg = tier2_agg.setdefault(t.original, {
                        "original": t.original, "approved": t.approved,
                        "category": t.category, "candidates": t.candidates,
                        "specific": t.specific,
                        "unmet": 0, "met": 0, "total": 0, "examples": [],
                    })
                    agg["unmet"] += unmet_pos
                    agg["met"] += met
                    agg["total"] += unmet_pos + met
                    room = 3 - len(agg["examples"])
                    if room > 0:
                        agg["examples"].extend(unmet_rows[:room])

        # ── B. 勿用残留 ──
        if want_forbidden:
            pairs = []
            okforms = {}          # 原文 → 该术语所有"合规字面"，用于排除子串误报
            for t in terms:
                for f in t.forbidden:
                    pairs.append((f, t.original, t.approved))
                okforms.setdefault(t.original, set()).update(t.simple)
                if t.approved:
                    okforms[t.original].add(t.approved)
            for orig, info in (extra_pairs or {}).items():
                for f in info.get("forbidden", []):
                    pairs.append((f, orig, info.get("approved", "")))
                if info.get("approved"):
                    okforms.setdefault(orig, set()).add(info["approved"])
            dst_text = "\n".join(dst_lines)
            dst_lower = dst_text.lower()
            dst_idx = LineIndex(dst_text)
            for needle, original, approved in pairs:
                nl, start = needle.lower(), 0
                while True:
                    pos = dst_lower.find(nl, start)
                    if pos < 0:
                        break
                    start = pos + len(nl)
                    L = dst_idx.line(pos)
                    if exc.covers(n, L, original):
                        continue
                    # 子串误报过滤：旧译"电讯报"落在规范译法《每日电讯报》内部时，
                    # 不是残留，而是"旧译是规范译法的子串"。检查该处是否被某个
                    # 含此旧译的合规字面覆盖，覆盖则跳过。
                    covered = False
                    for form in okforms.get(original, ()):
                        fl = form.lower()
                        if not fl or nl not in fl:
                            continue
                        # 上界必须留出整个 form 的长度，否则"跨过 pos 的规范译法"
                        # 整体落在切片之外、rfind 返回 -1（曾经的 bug）。
                        s0 = dst_lower.rfind(fl, 0, pos + len(fl))
                        if s0 >= 0 and s0 <= pos and s0 + len(fl) >= pos + len(nl):
                            covered = True
                            break
                    if covered:
                        continue
                    forbidden_hits.append({
                        "chunk": n, "line": L, "original": original,
                        "approved": approved, "found": needle,
                        "target": dst_lines[L - 1].strip() if L - 1 < len(dst_lines) else "",
                    })

        # ── C. 提醒词 ──
        if want_watch:
            for i, line in enumerate(dst_lines, 1):
                for w in watch_words:
                    if w in line:
                        idx = line.find(w)
                        watch_hits.append({
                            "chunk": n, "line": i, "word": w, "target": line.strip(),
                            "snippet": line[max(0, idx - 20):idx + len(w) + 20].strip(),
                        })

    return {
        "tier1": tier1, "tier2": list(tier2_agg.values()),
        "forbidden": forbidden_hits,
        "watch": watch_hits, "parity_bad": parity_bad, "missing": missing,
        "stats": stats,
    }


def check_review_final_divergence(book_dir: Path, chunk_nums: list):
    out = []
    for n in chunk_nums:
        r = book_dir / "temptranslations" / ("chunk-%03d.review.txt" % n)
        f = book_dir / "translations" / ("chunk-%03d.txt" % n)
        if r.is_file() and f.is_file():
            if r.read_text(encoding="utf-8-sig") != f.read_text(encoding="utf-8-sig"):
                out.append(n)
    return out


# ────────────────────────────────────────────────────────────────────────
# D. 术语发现
# ────────────────────────────────────────────────────────────────────────

PHRASE_RE = re.compile(r"[A-Za-z][A-Za-z0-9’'\-]*(?:\s+[A-Za-z][A-Za-z0-9’'\-]*){0,3}")


def normalize_phrase(p: str) -> str:
    p = p.lower().replace("’", "'")
    p = re.sub(r"[\u2010-\u2015\-]+", " ", p)
    return re.sub(r"\s+", " ", p).strip()


def do_discover(book_dir: Path, chunk_nums: list, terms: list, min_count: int, top: int):
    glossed = {normalize_phrase(t.original) for t in terms}
    counts, chunks_seen, example = {}, {}, {}
    for n in chunk_nums:
        f = book_dir / "chunks" / ("chunk-%03d.txt" % n)
        if not f.is_file():
            continue
        text = f.read_text(encoding="utf-8-sig")
        for m in PHRASE_RE.finditer(text):
            ph = normalize_phrase(m.group(0))
            if not ph:
                continue
            counts[ph] = counts.get(ph, 0) + 1
            chunks_seen.setdefault(ph, set()).add(n)
            example.setdefault(ph, (n, text[:m.start()].count("\n") + 1))
    rows = []
    for ph, c in counts.items():
        if c < min_count or ph in glossed:
            continue
        words = ph.split()
        if all(w in COMMON_WORDS for w in words):
            continue
        if words[0] in COMMON_WORDS:
            continue          # 虚词开头（the/of/a/for…）几乎必是噪音
        if len(words) == 1 and len(ph) < 6:
            continue
        rows.append((c, len(chunks_seen[ph]), ph, example[ph]))
    rows.sort(key=lambda r: (-r[0], -r[1], r[2]))
    return rows[:top]


# ────────────────────────────────────────────────────────────────────────
# F. 候选/包含关系冲突检查（"兜底"检查）
#
# 动机：位置对位的判定是"译文行是否 **包含** 规范译法"。因此当【规范译法是
# 某个错误写法（或被另一条规则认定为合规的写法）的子串】时，对位检查**必然失效**：
#     · 规范「鹈鹕」，实际写成「鹈鹕图书」→ 含「鹈鹕」→ 判合规（真事，本轮抓到 3 处）
#     · 规范「莫」，  实际写成「莫乌」    → 含「莫」  → 判合规（真事）
# 这类地方是漂移最容易藏身之处，机器判不了，只能把可疑组合**列给人看**。
#
# 三类：
#   A｜自相矛盾（必须修）——同一行内，规范译法 与 候选/勿用 互为包含。
#        等于同时宣布"这么写可以"和"这么写不行"，两条规则打架，必须改掉一边。
#   B｜跨行冲突（须复核）——一条的 规范译法 是另一条的 勿用（任一方向）；
#        或一条的 候选 是另一条的 规范/勿用。同样是规则打架。
#   C｜包含遮蔽（提示）——两条的 规范译法 互为包含（不同行）。再分：
#        C1 原文也不同源 → 最需警惕（两个不相干的术语共用同一串）
#        C2 原文同源     → 复合术语常规（支配型 ⊂ 支配型游戏），一般无需改动
# ────────────────────────────────────────────────────────────────────────

_ALL_BM = "《》〈〉「」『』“”\"'‘’ \t"

def clean_value(s: str) -> str:
    """清掉**所有**书名号/引号字符（不只是首尾），供包含关系比较使用。

    strip_bookmarks 只去首尾，于是「《时代》杂志」会留下中间那个「》」——
    比较虽仍可用，但显示难看、且对「时代》杂志」这类残留做比较容易误判。
    """
    s = (s or "").strip()
    for ch in _ALL_BM:
        s = s.replace(ch, "")
    return s.strip()


def _collide_entries(terms: list) -> list:
    """收集参与比较的所有"译文字面"：[(kind, term, value)]，kind ∈ approved/candidate/forbidden。"""
    out, seen = [], set()
    for t in terms:
        base = clean_value(t.approved)
        vals = []
        if base:
            vals.append(("approved", base))
            nop = strip_parens(base)
            if nop and nop != base:
                vals.append(("approved", nop))
        for c in t.candidates:
            cb = clean_value(c)
            if cb:
                vals.append(("candidate", cb))
        for f in t.forbidden:
            fb = clean_value(f)
            if fb:
                vals.append(("forbidden", fb))
        for kind, v in vals:
            if len(v) < 2:
                continue
            key = (kind, t.original, v)
            if key in seen:
                continue
            seen.add(key)
            out.append((kind, t, v))
    return out


def count_source_positions(book_dir: Path, nums: list, terms: list) -> dict:
    """统计每个术语在源文中的出现次数（用于给冲突排序、评估风险）。"""
    counts = {}
    for n in nums:
        f = book_dir / "chunks" / ("chunk-%03d.txt" % n)
        if not f.is_file():
            continue
        text = f.read_text(encoding="utf-8-sig")
        low = text.lower()
        for t in terms:
            if not t.regex or t.needle not in low:
                continue
            c = sum(1 for _ in t.regex.finditer(text))
            if c:
                counts[t.original] = counts.get(t.original, 0) + c
    return counts


def self_contradictions(terms: list) -> list:
    """A 类真矛盾：同一行内【候选】与【勿用】互为包含（或完全相同）。

    为什么只有这一对才算矛盾：
      · 规范 ⊂ 候选（如「港务局」⊂「纽约与新泽西港务局」）是【长短形式并存】，
        常见且正当——登记候选的本意正是"短形式也接受"，不是矛盾。
      · 规范 ⊂ 勿用（如「电讯报」⊂「每日电讯报」）是有意的【弃用长形】，
        也不是矛盾（勿用检查已带子串过滤，不会误伤规范译法）。
      · 只有【候选】与【勿用】打架＝同一行同时宣布"可以这么写"与"不可以这么写"，
        这是登记失误，必须修。
    """
    bad, seen = [], set()
    for t in terms:
        cand = [v for v in (clean_value(c) for c in t.candidates) if len(v) >= 2]
        forb = [v for v in (clean_value(f) for f in t.forbidden) if len(v) >= 2]
        for a in cand:
            for b in forb:
                if a == b or a in b or b in a:
                    row = (t.original, "候选", a, "勿用", b)
                    if row not in seen:
                        seen.add(row)
                        bad.append(row)
    return bad


def collision_report(book_dir: Path, nums: list, terms: list):
    """完整冲突报告：A / B / C1 / C2 四桶。"""
    ent = _collide_entries(terms)
    counts = count_source_positions(book_dir, nums, terms)
    A, B, C1, C2 = [], [], [], []

    # A｜同一行的自相矛盾
    for original, ki, vi, kj, vj in self_contradictions(terms):
        A.append((original, ki, vi, kj, vj))

    # B/C｜跨行
    by_row = {}
    for kind, t, v in ent:
        by_row.setdefault(t.original, []).append((kind, v))

    C, D = [], []
    for i in range(len(ent)):
        ki, ti, vi = ent[i]
        for j in range(len(ent)):
            if i == j:
                continue
            kj, tj, vj = ent[j]
            if vi == vj or vi not in vj:
                continue                      # 只看"短 ⊂ 长"方向
            if ti.original == tj.original:
                # 同一行内的"长短并存"与"有意弃用"——通常是正当手法，作提示
                if {ki, kj} == {"approved", "candidate"}:
                    C.append((vi, ti.original, ki, vj, kj))
                elif {ki, kj} == {"approved", "forbidden"}:
                    D.append((vi, ti.original, vj))
                continue
            # 跨行包含：短串会被长串遮蔽，按【短侧术语的源文出现次数】排序
            # （短侧出现得越多，遮蔽面越大，越值得先看）
            B.append((vi, ti.original, ki, vj, tj.original, kj))

    def uniq(rows):
        seen, out = set(), []
        for r in rows:
            if r in seen:
                continue
            seen.add(r)
            out.append(r)
        return out

    A, B, C, D = uniq(A), uniq(B), uniq(C), uniq(D)

    def arrow(a, ka, b, kb):
        return "%s（%s） ⊂ %s（%s）" % (a, ka, b, kb)

    print("===== 候选/包含关系冲突检查 ｜ %s =====" % book_dir.name)
    print("术语表 %d 行；参与比较的字面 %d 条" % (len(terms), len(ent)))
    print("说明：对位判定靠【译文行是否包含规范译法】。若规范译法是某个错误写法")
    print("      或其他条目的合规写法的子串，对位检查必然失效——下列组合即为该处。\n")

    print("【A｜自相矛盾（必须修）】%d 组" % len(A))
    for original, ki, vi, kj, vj in A:
        print("  ✗ 原文「%s」：%s —— 同时宣布「可以这么写」与「不可以这么写」，规则打架"
              % (original, arrow(vi, ki, vj, kj)))
    if not A:
        print("  ✓ 无")

    # B 类按【短术语】归组显示：一个短术语被哪些更长的术语包含，
    # 比罗列 95 条单独的组合好读得多。按短术语的源文出现次数排序——出现越多，
    # 被遮蔽的面越大，越该先看。
    by_short = {}
    for vi, oi, ki, vj, oj, kj in B:
        by_short.setdefault((oi, vi, ki), []).append((vj, oj, kj))
    order = sorted(by_short.items(), key=lambda kv: -counts.get(kv[0][0], 0))
    print("\n【B｜跨行包含遮蔽（须复核·漂移最易藏身处）】短术语 %d 个 / 共 %d 组"
          % (len(order), len(B)))
    shown = 0
    for (oi, vi, ki), longs in order:
        print("  ! 「%s」(原文 %s, %s, 源文 %d 处) 被 %d 个更长术语包含："
              % (vi, oi, ki, counts.get(oi, 0), len(longs)))
        for vj, oj, kj in longs[:6]:
            print("        ⊂ 「%s」(%s, %s)" % (vj, oj, kj))
        if len(longs) > 6:
            print("        …等 %d 个" % len(longs))
        shown += 1
        if shown >= 18:
            break
    if len(order) > shown:
        print("  …其余 %d 个短术语略" % (len(order) - shown))
    if not B:
        print("  ✓ 无")

    print("\n【C｜同行长短并存（提示·通常是正当手法）】%d 组" % len(C))
    for vi, oi, ki, vj, kj in C[:20]:
        print("  · 「%s」(%s) ⊂ 「%s」(%s) —— 原文「%s」" % (vi, ki, vj, kj, oi))
    if len(C) > 20:
        print("  …（共 %d 组，其余略）" % len(C))
    if not C:
        print("  ✓ 无")

    print("\n【D｜勿用超串警示（提示）】%d 组" % len(D))
    for vi, oi, vj in D[:12]:
        print("  · 原文「%s」：勿用「%s」是规范「%s」的超串" % (oi, vj, vi))
        print("      含义：勿用检查会命中规范译法内部（如「电讯报」命中《每日电讯报》）；")
        print("      脚本已内置子串过滤，换用其他工具时需自行注意。")
    if not D:
        print("  ✓ 无")

    print("\n" + "=" * 62)
    print("裁定：A %d 组须修（候选与勿用打架）；B %d 组为跨行遮蔽点，建议逐个复核"
          % (len(A), len(B)))
    print("      C/D 为提示，通常无需改动。")
    return len(A), len(B), len(B)


# ────────────────────────────────────────────────────────────────────────
# 主入口
# ────────────────────────────────────────────────────────────────────────

def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    ap = argparse.ArgumentParser(
        description="跨块一致性扫描器 v2.1：术语位置对位（两层）＋ 勿用残留 ＋ 提醒词 ＋ 术语发现")
    ap.add_argument("-s", "--slug", required=True, help="书目 slug")
    ap.add_argument("-r", "--root", default=None, help="工作区根目录")
    ap.add_argument("--stage", choices=["final", "review", "both"], default="final",
                    help="译文来源：final=translations/(默认)，review=审校稿，both=再查分歧")
    ap.add_argument("--from", dest="from_", type=int, default=0, help="起始块号")
    ap.add_argument("--to", type=int, default=None, help="结束块号")
    ap.add_argument("--term", default=None, help="只检查指定术语原文（逗号分隔）")
    ap.add_argument("--tier1", default=None,
                    help="把指定术语强制提升到一层逐位置问责（逗号分隔，如 virtuosi）")
    ap.add_argument("--watch-words", default=None, help="该书专属提醒词表 TSV")
    ap.add_argument("--term-pairs", default=None, help="外部术语对 JSON（补充勿用）")
    ap.add_argument("--no-glossary", action="store_false", dest="glossary",
                    help="关闭术语对位检查(A)")
    ap.add_argument("--no-forbidden", action="store_false", dest="forbidden",
                    help="关闭勿用残留检查(B)")
    ap.add_argument("--format", choices=["summary", "detail", "tsv"],
                    default="summary", help="输出格式")
    ap.add_argument("--collisions", action="store_true",
                    help="候选/包含关系冲突检查（只跑 F）：列出「规范译法是别的写法子串」的组合")
    ap.add_argument("--discover", action="store_true", help="术语发现模式（只跑 D）")
    ap.add_argument("--discover-min", type=int, default=12, help="发现模式最小出现次数")
    ap.add_argument("--discover-top", type=int, default=50, help="发现模式最多列出条数")
    ap.add_argument("--strict-all", action="store_true",
                    help="把 Tier 2 也计入退出码")
    ap.add_argument("--exit-zero", action="store_true", help="始终返回 0")
    args = ap.parse_args()

    root = Path(args.root) if args.root else Path(__file__).resolve().parent
    book_dir = root / "books" / args.slug
    if not book_dir.is_dir():
        print("错误: 书目目录不存在: %s" % book_dir)
        return 1

    terms = parse_glossary(book_dir / "glossary.md")
    if args.term:
        want = {x.strip().lower() for x in args.term.split(",") if x.strip()}
        terms = [t for t in terms if t.original.lower() in want]
        if not terms:
            print("错误: --term 指定的术语在 glossary.md 中找不到")
            return 1

    chunks_dir = book_dir / "chunks"
    nums = sorted(int(re.match(r"chunk-(\d{3})\.txt$", p.name).group(1))
                  for p in chunks_dir.iterdir()
                  if re.match(r"chunk-(\d{3})\.txt$", p.name))
    nums = [n for n in nums if n >= args.from_ and (args.to is None or n <= args.to)]
    if not nums:
        print("错误: 指定范围内没有源文块")
        return 1
    lo, hi = nums[0], nums[-1]

    if args.collisions:
        nA, nB, nC1 = collision_report(book_dir, nums, terms)
        if args.exit_zero:
            return 0
        return 2 if (nA or nB) else 0

    if args.discover:
        print("发现模式：chunk-%03d..chunk-%03d，最小出现 %d 次" % (lo, hi, args.discover_min))
        rows = do_discover(book_dir, nums, terms, args.discover_min, args.discover_top)
        print("glossary.md 已收录 %d 条术语\n" % len(terms))
        print("出现次数  跨块数  英文短语                            首现")
        print("-" * 78)
        for c, nc, ph, (cn, cl) in rows:
            print("%8d  %6d  %-35s chunk-%03d:L%d" % (c, nc, ph, cn, cl))
        print("-" * 78)
        print("共 %d 条候选（启发式，供人工筛选后补录 glossary.md）" % len(rows))
        return 0

    exc = Exceptions(book_dir / ".scan-exceptions")
    watch_words = DEFAULT_WATCH_WORDS[:]
    if args.watch_words:
        watch_words = load_watch_words(Path(args.watch_words))
    extra_pairs = load_term_pairs(Path(args.term_pairs)) if args.term_pairs else {}
    promote = {x.strip().lower() for x in args.tier1.split(",")} if args.tier1 else set()

    n_specific = sum(1 for t in terms if t.specific)
    print("===== %s ｜ chunk-%03d..chunk-%03d ｜ 译文来源: %s ====="
          % (args.slug, lo, hi, args.stage))
    print("glossary.md: %d 条术语（其中高辨识度 %d 条可进一层问责）%s"
          % (len(terms), n_specific, "；--term 过滤生效" if args.term else ""))
    if exc.count:
        print("例外登记: %d 条（books/%s/.scan-exceptions）" % (exc.count, args.slug))
    print("提醒词: %s" % ("%d 个（命中仅为提示，非判定）" % len(watch_words)
                          if watch_words else "未启用（默认不启用；用 --watch-words 指定该书专属表）"))
    print("")

    r = scan(book_dir, terms, nums, args.stage, watch_words, extra_pairs, exc,
             args.glossary, args.forbidden, bool(watch_words), promote)

    print("【前置守卫】源文/译文行·空行对位")
    if r["parity_bad"]:
        print("  ✗ 对位前提不成立、已跳过逐位置问责的块 %d 个:" % len(r["parity_bad"]))
        for n, a, b in r["parity_bad"][:10]:
            print("      chunk-%03d: 源文 %d 行 / 译文 %d 行" % (n, a, b))
        if len(r["parity_bad"]) > 10:
            print("      …（共 %d 个）" % len(r["parity_bad"]))
    else:
        print("  ✓ 全部 %d 块行数与空行模式一致，位置对位可用"
              % (len(nums) - len(r["missing"])))
    if r["missing"]:
        print("  · 缺文件的块: %s" % ", ".join("chunk-%03d" % n for n in r["missing"]))

    s = r["stats"]
    print("")
    print("【A 术语对位】源文命中 %d 处（涉及 %d 条术语），逐一问责 %d 处"
          % (s["positions"], s["terms_present"], s["positions"]))
    print("  一层 Tier 1｜位置漂移（须裁定）: %d 处" % len(r["tier1"]))
    print("  二层 Tier 2｜术语表口径与正文不符（供对表）: %d 条术语"
          % len(r["tier2"]))
    print("")
    print("【B 勿用残留】%s"
          % ("✗ %d 处" % len(r["forbidden"]) if r["forbidden"] else "✓ 0 处"))
    print("【C 提醒词】%s" % ("%d 处（提示，不需修正）" % len(r["watch"])
                              if watch_words else "未启用"))

    diverge = []
    if args.stage == "both":
        diverge = check_review_final_divergence(book_dir, nums)
        print("【E 审校稿/成品分歧】%s"
              % ("✗ %s" % ", ".join("chunk-%03d" % n for n in diverge) if diverge
                 else "✓ 逐字一致"))

    fmt = args.format

    if r["tier1"]:
        if fmt == "tsv":
            print("\n类型\t块\t行\t原文\t规范译法\t候选\t该行实际内容")
            for h in r["tier1"]:
                print("位置漂移\tchunk-%03d\t%d\t%s\t%s\t%s\t%s"
                      % (h["chunk"], h["line"], h["original"], h["approved"],
                         "／".join(h["candidates"]), h["target"]))
        else:
            print("")
            print("───── 一层 Tier 1：位置漂移明细（同一术语此处未合口径、别处合口径）─────")
            for h in r["tier1"]:
                print("  ✗ chunk-%03d:L%d  「%s」应含「%s」%s"
                      % (h["chunk"], h["line"], h["original"], h["approved"],
                         ("（候选: %s）" % "／".join(h["candidates"])) if h["candidates"] else ""))
                if fmt == "detail":
                    print("      源文: %s" % h["src"][:110])
                    print("      译文: %s" % h["target"][:110])
                else:
                    print("      译文: %s" % h["target"][:90])

    if r["tier2"]:
        if fmt == "tsv":
            for h in r["tier2"]:
                print("表与正文不符\t-\t%d/%d\t%s\t%s\t%s\t%s"
                      % (h["unmet"], h["total"], h["original"], h["approved"],
                         "／".join(h["candidates"]),
                         " | ".join("chunk-%03d:L%d" % (e["chunk"], e["line"])
                                    for e in h["examples"])))
        else:
            print("")
            print("───── 二层 Tier 2：术语表口径与正文不符（按术语汇总，不分位置刷屏）─────")
            for h in sorted(r["tier2"], key=lambda x: -x["unmet"]):
                tag = "高辨识度但全书未合口径" if h["specific"] else "日常词/泛用词"
                print("  · %s → 表中作「%s」；源文出现 %d 次，其中 %d 次未合口径（%s）"
                      % (h["original"], h["approved"], h["total"], h["unmet"], tag))
                if h["candidates"]:
                    print("      候选: %s" % "／".join(h["candidates"]))
                for e in h["examples"]:
                    print("      chunk-%03d:L%d  译文: %s"
                          % (e["chunk"], e["line"], e["target"][:80]))

    if r["forbidden"]:
        if fmt == "tsv":
            for h in r["forbidden"]:
                print("勿用残留\tchunk-%03d\t%d\t%s\t%s\t%s\t%s"
                      % (h["chunk"], h["line"], h["original"], h["approved"],
                         h["found"], h["target"]))
        else:
            print("")
            print("───── 勿用残留明细 ─────")
            by = {}
            for h in r["forbidden"]:
                by.setdefault((h["original"], h["found"]), []).append(h)
            for (orig, found), hits in sorted(by.items(), key=lambda x: -len(x[1])):
                print("  ✗ %s 勿用「%s」（应「%s」）: %d 处"
                      % (orig, found, hits[0]["approved"], len(hits)))
                print("      %s" % ", ".join("chunk-%03d:L%d" % (h["chunk"], h["line"])
                                             for h in hits))

    if r["watch"]:
        by = {}
        for h in r["watch"]:
            by.setdefault(h["word"], []).append(h)
        print("")
        print("───── 提醒词汇总（提示，非判定）─────")
        for w, hits in sorted(by.items(), key=lambda x: -len(x[1])):
            print("  「%s」: %d 处（%d 块）"
                  % (w, len(hits), len({h["chunk"] for h in hits})))

    # ── F. 自相矛盾速查（A 类；便宜，常规运行顺带跑）──
    self_contra = self_contradictions(terms) if args.glossary else []
    print("")
    if self_contra:
        print("【F 候选/包含关系】A 类自相矛盾 %d 组（必须修；完整报告见 --collisions）"
              % len(self_contra))
        for original, ki, vi, kj, vj in self_contra[:5]:
            print("  ✗ 原文「%s」：%s（%s） ⊂ %s（%s）" % (original, vi, ki, vj, kj))
        if len(self_contra) > 5:
            print("  …（共 %d 组）" % len(self_contra))
    else:
        print("【F 候选/包含关系】A 类自相矛盾 0 组")

    findings = len(r["tier1"]) + len(r["forbidden"]) + len(diverge) + len(self_contra)
    print("")
    print("=" * 62)
    if findings == 0:
        print("裁定: 通过 —— 无位置漂移、无勿用残留")
        print("说明: 零命中＝术语表覆盖到的术语，凡有一处合口径的，其每一处都合口径。")
        print("      术语表自身的覆盖度请看 --discover；Tier 2 若不为 0，"
              "那是表与正文的写法分歧，另行对表。")
    else:
        print("裁定: %d 项待裁定（位置漂移 %d ＋ 勿用残留 %d%s）"
              % (findings, len(r["tier1"]), len(r["forbidden"]),
                 " ＋ 审校稿/成品分歧 %d" % len(diverge) if diverge else ""))
        print("提示: --format detail 看上下文；确认属合理变体则登记 "
              "books/%s/.scan-exceptions" % args.slug)
    if r["tier2"]:
        print("另有 Tier 2 %d 条术语待对表（不计入退出码；--strict-all 可计入）"
              % len(r["tier2"]))
    print("=" * 62)

    if args.exit_zero:
        return 0
    if args.strict_all:
        findings += len(r["tier2"])
    return 0 if findings == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
