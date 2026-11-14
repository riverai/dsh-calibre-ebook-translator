#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
glossary-append.py — 术语表追加 / 编辑工具

用途：往 glossary.md 追加新行（append 模式）或修改已有行的译文/备注
      （edit 模式），遵循协议的 append-only + corrective-only 原则：
      追加新行不覆盖旧行；修改已有行时旧值移入备注（勿用:X），不删行。

用法：
    # 追加新行（TSV：原文\\t译文\\t类别\\t首现块\\t备注）
    python glossary-append.py -s storyscience append _gloss.tsv

    # 编辑已有行（按原文列定位，替换译文列，旧值移入备注）
    python glossary-append.py -s storyscience edit _edit.tsv

    # 编辑备注列（按原文列定位，替换备注列，旧值追加"→ 新值"）
    python glossary-append.py -s storyscience edit-note _note.tsv

    # 交互式追加单行
    python glossary-append.py -s storyscience add-row "Jonathan Haidt" "乔纳森·海特" "人名" "001" "心理学家"

参数：
    -s/--slug    书目 slug（books/<slug>/ 下）
    -r/--root    工作区根目录；缺省为脚本所在目录
    子命令：append | edit | edit-note | add-row

编辑清单格式（TSV，制表符分隔，UTF-8，无 BOM）：
    append 模式：  原文\\t译文\\t类别\\t首现块\\t备注
    edit 模式：    原文\\t新译文\\t说明（旧值自动移入备注）
    edit-note 模式：原文\\t新备注\\t说明（旧备注追加→新备注）

════════════════════════════════════════════════════════════════════════
【术语表规范格式】—— 唯一权威定义，务必遵守（lint 子命令可校验）
════════════════════════════════════════════════════════════════════════
一、表结构（固定 5 列，不得增删改序）
    | 原文 | 译文 | 类别 | 首现块 | 备注 |
    · 类别 ∈ {人名, 地名, 组织, 术语, 物品, 其他}
    · 首现块 = 3 位块号（如 026）；补译/订正过的在其备注里写"订正:"
    · **任何单元格内都不得出现半角竖线 `|`**——它会撑破表格、导致解析时
      备注尾部被静默丢弃（本工具历史上就踩过：用了 ` | ` 作分隔符，把
      statusgame 15 行、storydeal 1 行撑成 6/8 列）。工具会自动把 `|` 换成 `／`。

二、备注列（备注的微语法 —— 只有下面这些是"有语义的"，其余为自由说明）
    候选:译法A、译法B      可选译法。位置对位检查【命中其一即算合规】。
                           登记前先跑 scan-consistency.py --collisions，
                           自相矛盾（候选与勿用打架）会被 A 类直接拦下。
    勿用:旧译法            废弃译法。出现即报（勿用残留检查）。
    订正:2026-11-11 说明    订正记录。旧值一并留在本行，不删行。
    源文:说明              源文笔误/原书特殊之处（如拼写有误、旧拼）
    自由说明               其余内容按需写，放最后
    · 分隔符统一用【全角分号 ；】。禁止用 ` | `（撑破表格）。
    · 标记词后用【半角冒号 :】。历史写法「勿用：」「候选：」（全角冒号）
      视为不合规，normalize 子命令会统一。
    · 禁止 markdown（`**加粗**` 会被 normalize 剥掉）。
    · 不要用括号包裹标记：写 `候选:X`，不写 `(候选:X)`。

三、语义约定（工具据此判定，别写错）
    · 译文 = 唯一【规范译法】。一条原文只能有一个规范译法。
    · 候选 = "这么写也算对"（放宽判定）；勿用 = "这么写就算错"（收紧判定）。
      两者不能同时命中同一字面 —— 那是自相矛盾。
    · 一个术语行的规范译法若与另一行的更长译法构成【包含关系】
      （如「鹈鹕」⊂「鹈鹕图书」），该处的位置对位检查必然失效
      （漂移会被遮蔽）。--collisions 的 B 类专门列这种组合。
════════════════════════════════════════════════════════════════════════

lint 用法（只读校验，不改文件）：
    python glossary-append.py -s <slug> lint
    → 报告列数异常行、非规范标记（全角冒号/括号包裹/markdown/竖线）等
normalize 用法（机械规范化，改动前请先跑 lint 看一眼）：
    python glossary-append.py -s <slug> normalize
    → 只做格式修复，不动语义：
      · >5 列的行走反解：前 4 列归位，其余用「；」重新拼回备注
      · 单元格内 `|` → `／`
      · `勿用：`/`候选：`/`订正：`/`源文：` → 半角冒号
      · `(候选:X)` / `（候选:X）` → `候选:X`
      · `**X**` → `X`
      · 本工具旧版遗留的 ` | ` 备注分隔符 → `；`

安全机制：
    · append：新行的"原文"列若与已有行重复 → 警告（可能是误加重复行）
    · edit：按"原文"列定位；若找不到 → 报错退出；若找到多行 → 报错退出
    · edit 后旧译文自动移入备注列（格式："勿用:旧值 → 新值；说明"）
    · 不删除任何行

退出码：0 = 成功；1 = 部分失败或文件未改；2 = 参数/文件错误
"""

import argparse
import re
import sys
from datetime import date
from pathlib import Path

ALLOWED_CATEGORIES = {"人名", "地名", "组织", "术语", "物品", "其他"}
MARKER_WORDS = ("候选", "勿用", "订正", "源文")


def load_glossary(glossary_path: Path) -> list[str]:
    """读取 glossary.md，返回行列表。"""
    return glossary_path.read_text(encoding="utf-8").splitlines()


def save_glossary(glossary_path: Path, lines: list[str]) -> None:
    """写回 glossary.md（UTF-8，无 BOM，末尾换行）。"""
    text = "\n".join(lines)
    if not text.endswith("\n"):
        text += "\n"
    glossary_path.write_text(text, encoding="utf-8", newline="")


def parse_row(line: str) -> list[str] | None:
    """把一条管道表行拆成 5 列。返回 None 表示不是数据行（表头/分隔/空行）。"""
    ok, cells = split_row_raw(line)
    if not ok or not cells or cells[0] == "原文":
        return None
    if len(cells) < 5:
        return None
    return cells[:5]      # 原文, 译文, 类别, 首现块, 备注


def sanitize_cell(s: str) -> str:
    """单元格消毒：半角竖线 `|` 会撑破管道表（历史上真踩过），一律换成全角 `／`。

    另外把制表符与换行也换掉——它们同样会破坏 TSV/Markdown 结构。
    """
    s = (s or "").replace("|", "／")
    s = s.replace("\t", " ").replace("\n", " ").replace("\r", " ")
    return s.strip()


def make_row(original: str, translation: str, category: str,
             first_chunk: str, note: str) -> str:
    """构造一条管道表行（各单元格先消毒，确保永远是 5 列）。"""
    return "| %s | %s | %s | %s | %s |" % (
        sanitize_cell(original), sanitize_cell(translation),
        sanitize_cell(category), sanitize_cell(first_chunk),
        sanitize_cell(note))


def find_row_by_original(lines: list[str], original: str) -> tuple[int, list[str]] | None:
    """按"原文"列定位行。返回 (行索引, 拆分后的5列) 或 None。"""
    for i, line in enumerate(lines):
        cols = parse_row(line)
        if cols and cols[0] == original:
            return (i, cols)
    return None


# ── append 模式 ──

def cmd_append(glossary_path: Path, tsv_path: Path) -> int:
    """从 TSV 追加新行到 glossary.md 末尾。"""
    lines = load_glossary(glossary_path)
    existing_originals = set()
    for line in lines:
        cols = parse_row(line)
        if cols:
            existing_originals.add(cols[0])

    raw = tsv_path.read_text(encoding="utf-8-sig")  # 自动去 BOM
    new_rows = []
    n_added = 0
    n_dup = 0
    for raw_line in raw.splitlines():
        raw_line = raw_line.rstrip("\r")
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        parts = raw_line.split("\t")
        if len(parts) < 4:
            print(f"  警告: 跳过列数不足的行: {raw_line[:60]}", file=sys.stderr)
            continue
        original = parts[0].strip()
        translation = parts[1].strip()
        category = parts[2].strip()
        first_chunk = parts[3].strip()
        note = parts[4].strip().rstrip("\r") if len(parts) > 4 else ""
        if original in existing_originals:
            print(f"  [重复] 原文「{original}」已存在，跳过（如需修改请用 edit 模式）")
            n_dup += 1
            continue
        new_row = make_row(original, translation, category, first_chunk, note)
        new_rows.append(new_row)
        existing_originals.add(original)
        n_added += 1
        print(f"  [追加] {original} → {translation}")

    if new_rows:
        # 追加到最后一行之后
        # 确保末尾有内容行，然后追加
        while lines and not lines[-1].strip():
            lines.pop()
        lines.extend(new_rows)
        save_glossary(glossary_path, lines)
        print(f"\n已追加 {n_added} 行，跳过 {n_dup} 行重复。")
        return 0
    else:
        print(f"\n无新行可追加（{n_dup} 行重复跳过）。")
        return 1


# ── edit 模式 ──

def cmd_edit(glossary_path: Path, tsv_path: Path) -> int:
    """修改已有行的译文列，旧值移入备注列。"""
    lines = load_glossary(glossary_path)
    raw = tsv_path.read_text(encoding="utf-8-sig")
    n_edited = 0
    n_missing = 0
    edits = []
    for raw_line in raw.splitlines():
        raw_line = raw_line.rstrip("\r")
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        parts = raw_line.split("\t")
        if len(parts) < 2:
            print(f"  警告: 跳过列数不足的行: {raw_line[:60]}", file=sys.stderr)
            continue
        original = parts[0].strip()
        new_translation = parts[1].strip()
        reason = parts[2].strip().rstrip("\r") if len(parts) > 2 else ""
        edits.append((original, new_translation, reason))

    for original, new_translation, reason in edits:
        found = find_row_by_original(lines, original)
        if not found:
            print(f"  [未找到] 原文「{original}」不在术语表中")
            n_missing += 1
            continue
        idx, cols = found
        old_translation = cols[1]
        old_note = cols[4]
        if old_translation == new_translation:
            print(f"  [无变化] 原文「{original}」译文已是「{new_translation}」")
            continue
        # 旧值移入备注。规范格式：勿用:旧值；订正:日期 ...
        # ⚠ 绝不可用 " | " 拼接——半角竖线会撑破管道表，导致备注尾部被静默丢弃
        #   （本项目真实事故：曾把 statusgame 15 行撑成 6 列）。
        prefix = ("勿用:%s；订正:%s 译法由「%s」改为「%s」"
                  % (old_translation, date.today().isoformat(),
                     old_translation, new_translation))
        if reason:
            prefix += f"（{reason}）"
        new_note = f"{prefix}；{old_note}" if old_note else prefix
        lines[idx] = make_row(cols[0], new_translation, cols[2], cols[3], new_note)
        print(f"  [修改] {original}: {old_translation} → {new_translation}")
        print(f"         备注更新: {new_note[:80]}…")
        n_edited += 1

    if n_edited:
        save_glossary(glossary_path, lines)
        print(f"\n已修改 {n_edited} 行，{n_missing} 行未找到。")
        return 0
    else:
        print(f"\n无修改（{n_missing} 行未找到）。")
        return 1 if n_missing else 0


# ── edit-note 模式 ──

def cmd_edit_note(glossary_path: Path, tsv_path: Path) -> int:
    """修改已有行的备注列，旧备注追加 → 新备注。"""
    lines = load_glossary(glossary_path)
    raw = tsv_path.read_text(encoding="utf-8-sig")
    n_edited = 0
    n_missing = 0
    edits = []
    for raw_line in raw.splitlines():
        raw_line = raw_line.rstrip("\r")
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        parts = raw_line.split("\t")
        if len(parts) < 2:
            continue
        original = parts[0].strip()
        new_note = parts[1].strip()
        reason = parts[2].strip().rstrip("\r") if len(parts) > 2 else ""
        edits.append((original, new_note, reason))

    for original, new_note, reason in edits:
        found = find_row_by_original(lines, original)
        if not found:
            print(f"  [未找到] 原文「{original}」")
            n_missing += 1
            continue
        idx, cols = found
        old_note = cols[4]
        # 同样：用全角分号，不用 " | "（见 cmd_edit 处的说明）
        combined = new_note
        if old_note:
            combined = f"{new_note}；{old_note}"
        if reason:
            combined = f"{combined}；{reason}"
        lines[idx] = make_row(cols[0], cols[1], cols[2], cols[3], combined)
        print(f"  [备注] {original}: {combined[:80]}…")
        n_edited += 1

    if n_edited:
        save_glossary(glossary_path, lines)
        print(f"\n已更新备注 {n_edited} 行，{n_missing} 行未找到。")
        return 0
    else:
        print(f"\n无更新（{n_missing} 行未找到）。")
        return 1 if n_missing else 0


# ── add-row 模式（交互式单行追加）──

def cmd_add_row(glossary_path: Path, original: str, translation: str,
                category: str, first_chunk: str, note: str) -> int:
    """追加单行。"""
    lines = load_glossary(glossary_path)
    found = find_row_by_original(lines, original)
    if found:
        print(f"错误: 原文「{original}」已存在（如需修改请用 edit 模式）")
        return 1
    while lines and not lines[-1].strip():
        lines.pop()
    new_row = make_row(original, translation, category, first_chunk, note)
    lines.append(new_row)
    save_glossary(glossary_path, lines)
    print(f"已追加: {original} → {translation}")
    return 0


# ── lint / normalize 模式 ──

def split_row_raw(line: str):
    """拆行；返回 (是否数据行, 单元格列表)。

    与 parse_row 的区别：**不**在"恰好 5 列"上成立——正是为了能查出列数异常。
    """
    s = line.rstrip("\n")
    if not s.strip() or not s.startswith("|"):
        return (False, [])
    if set(s.strip()) <= set("|-: "):
        return (False, [])                       # 表头分隔行 |---|---|
    # 【关键】只按**未转义**的竖线切分：Markdown 里 `\|` 是单元内的字面竖线，
    # 不是列分隔符。早期版本直接 split("|")，会把一条合法行误判成列数异常。
    cells = [c.replace("\\|", "|").strip() for c in re.split(r"(?<!\\)\|", s)]
    if cells and cells[0] == "":
        cells = cells[1:]
    if cells and cells[-1] == "":
        cells = cells[:-1]
    return (True, cells)


def note_problems(note: str) -> list:
    bad = []
    if "|" in note:
        bad.append("备注含半角竖线（会撑破表格）")
    if "**" in note:
        bad.append("备注含 markdown 加粗 **")
    for m in MARKER_WORDS:
        if m + "：" in note:
            bad.append("标记用了全角冒号「%s：」" % m)
            break
    if re.search(r"[（(]\s*(候选|勿用|订正|源文)\s*[:：]", note):
        bad.append("标记被括号包裹")
    return bad


def fix_cell(s: str) -> str:
    """格式规范化（只动格式，不动语义；幂等）。"""
    s = s or ""
    s = s.replace(" | ", "；")                    # 旧版遗留的备注分隔符
    s = s.replace("|", "／")                      # 其余竖线一律换全角斜线
    s = s.replace("**", "")
    for m in MARKER_WORDS:
        s = s.replace(m + "：", m + ":")           # 全角冒号 → 半角
    # 只处理"括号里就是标记"的情形，避免误伤自由说明里的普通括号
    s = re.sub(r"[（(]\s*候选[:：]\s*([^（）()]*?)[）)]",
               lambda mo: "候选:" + "、".join(
                   p.strip() for p in re.split(r"[/、，,]", mo.group(1)) if p.strip()), s)
    s = re.sub(r"[（(]\s*勿用[:：]\s*([^（）()]*?)[）)]",
               lambda mo: "勿用:" + mo.group(1).strip(), s)
    s = re.sub(r"[（(]\s*订正[:：]\s*([^（）()]*?)[）)]",
               lambda mo: "订正:" + mo.group(1).strip(), s)
    return s.strip()


def lint_glossary(glossary_path: Path) -> int:
    """只读校验：列数、类别、首现块、备注微语法、原文重复。"""
    lines = load_glossary(glossary_path)
    n_data = 0
    n_err = 0          # 结构性错误：会造成数据丢失/解析失败
    n_warn = 0         # 风格警告：不合规范但无结构风险
    problems = []
    seen = {}
    for i, line in enumerate(lines, 1):
        ok, cells = split_row_raw(line)
        if not ok or (cells and cells[0] == "原文"):
            continue
        n_data += 1
        if len(cells) != 5:
            n_err += 1
            problems.append("[错误] L%-4d 列数=%d（应 5）—— 被竖线穿破或字段缺失: %s"
                            % (i, len(cells), line[:100]))
            continue                              # 列数不对，后续判定不可靠
        original, _tr, category, first, note = cells
        if category not in ALLOWED_CATEGORIES:
            n_warn += 1
            problems.append("[警告] L%-4d 类别「%s」不在枚举内（原文 %s）"
                            % (i, category, original))
        if re.fullmatch(r"\d{3}", first or ""):
            pass
        elif re.fullmatch(r"\d{1,2}", first or ""):
            n_warn += 1
            problems.append("[警告] L%-4d 首现块「%s」未补零（应 %s，normalize 可修）"
                            % (i, first, first.zfill(3)))
        else:
            n_err += 1
            problems.append("[错误] L%-4d 首现块「%s」不是 1–3 位数字（原文 %s）"
                            % (i, first, original))
        for p in note_problems(note):
            n_warn += 1
            problems.append("[警告] L%-4d %s（原文 %s）" % (i, p, original))
        if original in seen:
            n_warn += 1
            problems.append("[警告] L%-4d 原文「%s」重复（首次见 L%d）"
                            % (i, original, seen[original]))
        else:
            seen[original] = i

    print("===== 术语表 lint ｜ %s =====" % glossary_path.parent.name)
    print("数据行 %d 行" % n_data)
    print("  结构性错误（必须修）: %d" % n_err)
    print("  风格警告（应逐步收敛）: %d" % n_warn)
    if problems:
        errs = [p for p in problems if p.startswith("[错误]")]
        warns = [p for p in problems if p.startswith("[警告]")]
        if errs:
            print("\n----- 结构性错误（全部）-----")
            for p in errs[:40]:
                print("  " + p)
            if len(errs) > 40:
                print("  …（共 %d 条）" % len(errs))
        if warns:
            print("\n----- 风格警告（前 40 条）-----")
            for p in warns[:40]:
                print("  " + p)
            if len(warns) > 40:
                print("  …（共 %d 条）" % len(warns))
        print("\n裁定: %s。用 normalize 做机械修复（列数>5、首现块补零、标记写法）；"
              % ("不合规" if (n_err or n_warn) else "通过"))
        print("      列数<5 的行 normalize 不动，需人工补齐字段。")
    else:
        print("\n裁定: 通过 —— 结构与风格全部合规。")
    return 0 if (n_err == 0 and n_warn == 0) else 2


def normalize_glossary(glossary_path: Path) -> int:
    """格式规范化：修复被穿破的列、统一标记写法。只动格式，不动语义。"""
    lines = load_glossary(glossary_path)
    out = []
    n_rejoin = n_row = n_cell = 0
    manual = []
    for i, line in enumerate(lines, 1):
        ok, cells = split_row_raw(line)
        if not ok or (cells and cells[0] == "原文"):
            out.append(line)
            continue
        if len(cells) < 5:
            manual.append((i, len(cells), line))
            out.append(line)
            continue
        if len(cells) > 5:
            # 反解被竖线穿破的行：前 4 列归位，其余用「；」拼回备注
            cells = cells[:4] + ["；".join(c for c in cells[4:] if c)]
            n_rejoin += 1
        if re.fullmatch(r"\d{1,2}", cells[3] or ""):     # 首现块补零 89 → 089
            cells[3] = cells[3].zfill(3)
        fixed = []
        for c in cells:
            nc = fix_cell(c)
            if nc != c:
                n_cell += 1
            fixed.append(nc)
        new_line = make_row(*fixed)
        if new_line != line:
            n_row += 1
        out.append(new_line)

    if n_row:
        save_glossary(glossary_path, out)
    print("===== 术语表 normalize ｜ %s =====" % glossary_path.parent.name)
    print("  重建被穿破的行（>5 列）: %d" % n_rejoin)
    print("  单元格格式修正: %d" % n_cell)
    print("  实际改写的行: %d" % n_row)
    if manual:
        print("  ⚠ 列数<5、需人工补齐的行: %d" % len(manual))
        for i, n, line in manual[:10]:
            print("      L%d 列数=%d: %s" % (i, n, line[:100]))
    if not n_row and not manual:
        print("  无需改动。")
    return 0


# ── 主入口 ──

def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    ap = argparse.ArgumentParser(
        description="术语表追加/编辑工具（append-only + corrective-only）")
    ap.add_argument("-s", "--slug", required=True, help="书目 slug")
    ap.add_argument("-r", "--root", default=None, help="工作区根目录")
    ap.add_argument("command",
                    choices=["append", "edit", "edit-note", "add-row",
                             "lint", "normalize"],
                    help="子命令（lint/normalize 不需要 TSV）")
    ap.add_argument("file_or_args", nargs="*",
                    help="TSV 文件路径（append/edit/edit-note）或 5 个参数（add-row）")
    args = ap.parse_args()

    root = Path(args.root) if args.root else Path(__file__).resolve().parent
    glossary_path = root / "books" / args.slug / "glossary.md"
    if not glossary_path.is_file():
        print(f"错误: 术语表不存在: {glossary_path}")
        return 2

    if args.command == "lint":
        return lint_glossary(glossary_path)
    if args.command == "normalize":
        return normalize_glossary(glossary_path)

    if args.command == "add-row":
        if len(args.file_or_args) < 5:
            print("用法: add-row <原文> <译文> <类别> <首现块> <备注>")
            return 2
        return cmd_add_row(glossary_path, *args.file_or_args[:5])
    else:
        if not args.file_or_args:
            print("错误: 该子命令需要 TSV 文件路径")
            return 2
        tsv_path = Path(args.file_or_args[0])
        if not tsv_path.is_file():
            print(f"错误: TSV 文件不存在: {tsv_path}")
            return 2
        if args.command == "append":
            return cmd_append(glossary_path, tsv_path)
        elif args.command == "edit":
            return cmd_edit(glossary_path, tsv_path)
        elif args.command == "edit-note":
            return cmd_edit_note(glossary_path, tsv_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
