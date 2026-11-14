#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify-chunk.py — 单块译文的结构/标点/格式合规校验（只读，不改任何文件）

比对 源文 / 草稿 / 审校稿 / 成品，输出 PASS/FAIL 清单。
专门为"英文→中文"翻译项目设计（en dash – → 中文破折号 —— 等）。
不包含任何语言判断能力（禁词检测等超出脚本范畴）。

用法（在工作区根目录下运行）：
    # 单块
    python verify-chunk.py -s storyscience -c 16
    python verify-chunk.py -s storyscience -c 16 --diff
    python verify-chunk.py -s storyscience -c 16 \
        -a "史蒂文·斯皮尔伯格,（Steven Spielberg）" -x "斯蒂芬,老姑娘"

    # 批量（扫描所有已译块）
    python verify-chunk.py -s storyscience --all
    python verify-chunk.py -s storyscience --all --diff

参数：
  -s/--slug          书目 slug（books/<slug>/ 下）
  -c/--chunk         块号（0 基，等于 MCP chunk_id）
  -r/--root          工作区根目录；缺省为脚本所在目录
  -a/--assert        逗号分隔的"必须出现"字符串（仅单块模式）
  -x/--assert-absent 逗号分隔的"必须不出现"字符串（仅单块模式）
  --diff             额外列出 草稿→成品 的逐行差异
  --all              批量模式：自动发现并扫描所有已译块

退出码：0 = 全部 PASS；1 = 有 FAIL

检查项（均为纯文本/字节级，无语言判断）：
  结构：行数 / 非空块数 / 逐行空行模式
  标点：en dash 数目 + 逐行位置对应（– → ——）
        引号方向可能颠倒（WARN：”汉“ 模式——可能是连词夹引语，也可能真颠倒）
  格式：无 ASCII 直引号 / 无全角斜杠 / 无字面 \n / 无 markdown
        无 BOM / 无 tab / 无行尾空格
        引号嵌套（内层须用全角单引号 ‘’）
  对照：草稿→成品改动行数 / 审校稿→成品逐字一致
  断言：应存在 / 应已删除（仅单块模式）

WARN 的可见性（重要，防止调用方过滤输出时丢弃）：
  WARN（如"译文多出破折号，需人工裁定"）不改变退出码、不计入 FAIL，
  但会计数到块尾行与批量汇总行（"FAIL Y，WARN Z"）——即使只筛"批量汇总"
  也能看到 WARN 数。WARN>0 时必须逐条人工裁定后放行，不得无视。

已知限制（设计决策，非缺陷）：
  · 不做全角引号的行内配对/闭合检查。实测原因（74 块全量审计）：
    跨行引语的孤立闭引号（合法）、英文括注照录的英文引号（合法）、
    源文异常照录形态（如未闭合引号，已按源文保留）、三层嵌套
    “‘…“…”…’”（合法）——逐行配对模型对以上全部假阳性，故不做。
    方向颠倒检测（”汉“ 模式）以 WARN 级纳入（不是 FAIL）：
    合法假阳性为两段独立引语之间夹连词（如 ”或“ ”和“），真错误为
    同一对引语方向全反（如 ”旅人“ 应为 “旅人”），两者正则不可区分，故 WARN。
  · "无 ASCII 直引号"对英文括注内照录的英文原文双引号存在假阳性风险
    （本批未触发：英文引号已统一转全角或删除）。若未来触发，先确认
    该引号是否属"应保留的英文原文"，再决定例外或改写。
  · 注释页论文题名括注的英文单引号形态（‘…’ vs '…'）不检查——
    两种均属英文照录，体例统一属内容层面决策，超出脚本职责。

已批准例外（外部文件 books/<slug>/.verify-exceptions）：
  文学名句采用通行中译本时，其标点随译本，源文 en dash 可不对应。
  例外按"块号:行号"登记（行号为成品行号，1 基）。
  例外文件格式见下方 load_exceptions() 的注释。
  脚本不硬编码任何例外——每本书自己管理自己的例外，换书不改脚本。
"""

import argparse
import os
import re
import sys
from pathlib import Path


# ── 例外文件读取 ──────────────────────────────────────────
#
# 例外文件路径: books/<slug>/.verify-exceptions
# 每行格式:  块号:行号  原因
#   块号 = 3 位零填充（如 009）
#   行号 = 成品行号（1 基）
#   原因 = 空格后的任意文字（供人工审计）
# 以 # 开头的行为注释，空行忽略。
#
# 语义: 被登记的行**仅**从 en dash 数目/位置检查中豁免；
#       其他检查项（引号/BOM/tab/行尾空格等）仍正常检查。
#
# 登记原则（重要，防止滥用）:
#   · 仅当该行的 en dash 不对应属"已批准的翻译体例"时才登记（如文学名句用通行译本）。
#   · 不得用于掩盖译者真正擅加/遗漏的破折号——那是错误，不是例外。
#   · 每条例外必须有明确的人类可读原因。
#
# 示例:
#   # chunk-009 L5: 马克思《共产党宣言》开篇
#   009:5  采用中央编译局通行中译本，标点随译本
#
def load_exceptions(book_dir: Path) -> dict[str, str]:
    """读取 books/<slug>/.verify-exceptions，返回 { 'NNN:L': '原因' }。"""
    exc_file = book_dir / ".verify-exceptions"
    if not exc_file.is_file():
        return {}
    result = {}
    for raw in exc_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        # 格式: "NNN:L  原因" — 冒号后面第一个空格之前是 key，之后是 reason
        parts = line.split(None, 1)
        key = parts[0]
        reason = parts[1] if len(parts) > 1 else "(无原因)"
        result[key] = reason
    return result


# ── 工具函数 ──────────────────────────────────────────────

def read_lines(p: Path) -> list[str]:
    return p.read_text(encoding="utf-8").splitlines()


def read_bytes(p: Path) -> bytes:
    return p.read_bytes()


# ── 单块校验 ──────────────────────────────────────────────

def verify_chunk(root: Path, slug: str, chunk: int,
                 must: str = "", must_not: str = "",
                 show_diff: bool = False,
                 target: str = "final") -> tuple[int, int, int]:
    """
    校验单块，返回 (总项数, FAIL 数, 改动行数)。
    若文件缺失，返回 (-1, 1, -1)。

    target:
      "final"  — 校验 translations/chunk-NNN.txt（成品，默认）
      "review" — 校验 temptranslations/chunk-NNN.review.txt（审校稿）
      "draft"  — 校验 temptranslations/chunk-NNN.txt（草稿）
    """
    d = root / "books" / slug
    # 从外部文件加载例外（每本书自管理，脚本不硬编码）
    all_exc = load_exceptions(d)
    nn = f"{chunk:03d}"
    src = d / "chunks" / f"chunk-{nn}.txt"
    drf = d / "temptranslations" / f"chunk-{nn}.txt"
    rev = d / "temptranslations" / f"chunk-{nn}.review.txt"
    fin = d / "translations" / f"chunk-{nn}.txt"

    # 根据 target 选择被校验文件
    tgt_map = {"final": fin, "review": rev, "draft": drf}
    tgt = tgt_map.get(target, fin)
    tgt_label = {"final": "成品", "review": "审校稿", "draft": "草稿"}.get(target, "成品")

    if not src.is_file() or not tgt.is_file():
        missing = [p for p in (src, tgt) if not p.is_file()]
        print(f"  FATAL chunk-{nn}: 缺少文件 {missing}")
        return -1, 1, -1

    results = []
    warns = []   # WARN 明细（不计 FAIL、不改退出码，但计入尾行汇总）

    def check(name, ok, detail=""):
        results.append((name, bool(ok), detail))

    s_lines = read_lines(src)
    f_lines = read_lines(tgt)
    f_raw = read_bytes(tgt)
    s_txt = src.read_text(encoding="utf-8")
    f_txt = tgt.read_text(encoding="utf-8")

    # ── 1) 行数 / 块数 ──
    s_non = sum(1 for x in s_lines if x.strip())
    f_non = sum(1 for x in f_lines if x.strip())
    check(f"行数一致 (src={len(s_lines)} / {tgt_label}={len(f_lines)})",
          len(s_lines) == len(f_lines), "源文与译文行数必须相等")
    check(f"非空块数一致 (src={s_non} / {tgt_label}={f_non})",
          s_non == f_non, "blocks 不等，MCP 界面会黄色高亮")

    # ── 2) 逐行空行模式 ──
    if len(s_lines) == len(f_lines):
        bad = [i + 1 for i, (a, b) in enumerate(zip(s_lines, f_lines))
               if bool(a.strip()) != bool(b.strip())]
        check("逐行空行模式一致", not bad,
              "不一致行: " + ",".join(map(str, bad)) if bad else "OK")

    # ── 3) en dash 检查（分 FAIL 与 WARN 两级）──
    # 逻辑：
    #   · 源文有 en dash 但译文没有 → FAIL（漏译了原文标点，真错）
    #   · 源文没有但译文有"——" → WARN（可能是合理使用，也可能是擅加，需人工裁定）
    #   · 数目恰好一致 → PASS
    #   例外行（KNOWN_EXCEPTIONS / .verify-exceptions）从两侧扣除。
    exc_lines = {int(k.split(":")[1]) for k in all_exc
                 if k.startswith(f"{nn}:")}

    # 数字–数字 型 en dash 为页码/范围连接号（如索引 "114–15"），非标点破折号，
    # 不计入 en dash 检查（通用规则，与 026/042 例外同理）。
    NUM_DASH = re.compile(r"\d\s*–\s*\d")
    s_dash = s_txt.count("\u2013") - len(NUM_DASH.findall(s_txt))
    s_dash = max(0, s_dash) - sum(
        s_lines[i - 1].count("\u2013") for i in exc_lines if i <= len(s_lines))
    s_dash = max(0, s_dash)
    f_dash = f_txt.count("\u2014\u2014") - sum(
        f_lines[i - 1].count("\u2014\u2014") for i in exc_lines if i <= len(f_lines))
    exc_note = f"（扣除例外 {len(exc_lines)} 行）" if exc_lines else ""

    if s_dash == f_dash:
        check(f"en dash 数目 (src={s_dash} / fin={f_dash}){exc_note}",
              True, "OK")
    elif s_dash > f_dash:
        # 源文有但译文没有 → FAIL
        check(f"en dash 数目 (src={s_dash} / fin={f_dash}){exc_note}",
              False, f"源文有 {s_dash} 个 –，译文仅 {f_dash} 处——，漏译")
    else:
        # 译文多了 → WARN（计入 warns，不改退出码，但进尾行汇总）
        warns.append(f"en dash 数目: 译文多出 {f_dash - s_dash} 处——（可能擅加，需人工裁定）")

    if len(s_lines) == len(f_lines):
        pos_fail = []
        pos_warn = []
        NUMDASH = re.compile(r"\d\s*–\s*\d")  # 数字–数字 页码连接号，非标点
        for i, (a, b) in enumerate(zip(s_lines, f_lines), 1):
            if i in exc_lines:
                continue
            ca = a.count("\u2013") - len(NUMDASH.findall(a))
            cb = b.count("\u2014\u2014")
            if ca > cb:
                pos_fail.append(f"L{i}(src={ca}/fin={cb})")
            elif ca < cb:
                pos_warn.append(f"L{i}(src={ca}/fin={cb})")
        if pos_fail:
            check("en dash 位置", False, "漏译: " + " ".join(pos_fail))
        else:
            check("en dash 位置", True, "OK")
        if pos_warn:
            warns.append(f"en dash 位置: 译文多出 {' '.join(pos_warn)}（需人工裁定）")

    # ── 4) 格式卫生 ──
    check("无 ASCII 直引号", '"' not in f_txt, "引号须为中文全角")
    check("无全角斜杠", "\uff0f" not in f_txt, "斜杠须为 ASCII /")
    check("无字面 \\n", "\\n" not in f_txt, "须为真实换行")
    check("无 markdown", not re.search(r'\*\*|\|', f_txt), "纯文本输出")

    # BOM
    has_bom = f_raw[:3] == b'\xef\xbb\xbf'
    check("无 UTF-8 BOM", not has_bom, "成品文件不应有 BOM")

    # tab
    n_tab = f_txt.count("\t")
    check("无 tab", n_tab == 0, f"出现 {n_tab} 处" if n_tab else "OK")

    # 行尾空格
    n_trail = sum(1 for line in f_lines if line != line.rstrip())
    check("无行尾空格", n_trail == 0, f"出现 {n_trail} 处" if n_trail else "OK")

    # 引号嵌套：内层须用全角单引号 ‘’（U+2018/U+2019），不得用 ASCII '
    # 检测模式：全角双引号内出现 ASCII 单引号
    nested_bad = re.findall(r'\u201c[^\u201d]*\u0027[^\u201d]*\u201d', f_txt)
    check("引号嵌套（内层须全角单引号）", not nested_bad,
          f"发现 {len(nested_bad)} 处全角双引号内含 ASCII 单引号" if nested_bad else "OK")

    # 引号方向可能的颠倒：”汉“ / ’汉‘ —— 闭引号后紧跟纯汉字再跟开引号。
    # 实战中 chunk-073 曾把 “旅人” 打成 ”旅人“（方向全反），审校抓出但脚本漏检。
    # 该模式也存在大量合法假阳性（两段独立引语之间夹连词，如 ”或“ ”和“ ”与“），
    # 故定为 WARN 而非 FAIL——人工裁定后放行。
    inv = re.findall(r'\u201d[\u4e00-\u9fff]+\u201c', f_txt) \
        + re.findall(r'\u2019[\u4e00-\u9fff]+\u2018', f_txt)
    if inv:
        warns.append(f"引号方向可能颠倒 {len(inv)} 处: {' '.join(inv[:3])}（可能是连词夹在两段引语间的合法形态，也可能是方向颠倒——须人工裁定）")

    # ── 5) 草稿 / 审校稿 ──
    changed = None
    if drf.is_file():
        d_lines = read_lines(drf)
        check(f"草稿与成品行数一致 (草稿={len(d_lines)})",
              len(d_lines) == len(f_lines), "精准编辑不增删行")
        if len(d_lines) == len(f_lines):
            pairs = [i for i, (a, b) in enumerate(zip(d_lines, f_lines)) if a != b]
            changed = len(pairs)
            check(f"草稿→成品改动行数 ({changed})", True, "")
            if show_diff and pairs:
                print(f"\n--- chunk-{nn} 草稿→成品差异 ---")
                for i in pairs:
                    print(f"  L{i+1}")
                    print(f"    草稿: {d_lines[i]}")
                    print(f"    成品: {f_lines[i]}")

    if rev.is_file():
        check("审校稿→成品逐字一致",
              rev.read_text(encoding="utf-8") == f_txt,
              "成品应由审校稿复制而来")

    # ── 6) 断言（仅单块模式有意义）──
    if must:
        for s in filter(None, (t.strip() for t in must.split(","))):
            check(f"应存在: {s}", s in f_txt)
    if must_not:
        for s in filter(None, (t.strip() for t in must_not.split(","))):
            check(f"应已删除: {s}", s not in f_txt)

    # ── 输出 ──
    fail = sum(1 for _, ok, _ in results if not ok)
    for name, ok, detail in results:
        tag = "PASS" if ok else "FAIL"
        print(f"  {tag}  {name}" + (f"  {detail}" if not ok else ""))
    for w in warns:
        print(f"  WARN  {w}")

    print(f"  chunk-{nn}: {len(results)} 项，PASS {len(results)-fail}，FAIL {fail}"
          + (f"，WARN {len(warns)}" if warns else "")
          + (f"，改动 {changed} 行" if changed is not None else ""))
    if warns:
        print(f"  提示: WARN 不计 FAIL，但必须逐条人工裁定后放行，不得无视。")
    return len(results), fail, len(warns), changed if changed is not None else -1


# ── 批量模式 ──────────────────────────────────────────────

def find_chunks(root: Path, slug: str, target: str = "final") -> list[int]:
    """自动发现所有已有目标文件的块号，返回排序后的列表。"""
    dir_map = {"final": "translations", "review": "temptranslations", "draft": "temptranslations"}
    subdir = dir_map.get(target, "translations")
    # review 文件名为 chunk-NNN.review.txt，需特殊匹配
    pattern = r'chunk-(\d{3})\.review\.txt$' if target == "review" else r'chunk-(\d{3})\.txt$'
    tdir = root / "books" / slug / subdir
    if not tdir.is_dir():
        return []
    nums = []
    for f in tdir.iterdir():
        m = re.match(pattern, f.name)
        if m:
            nums.append(int(m.group(1)))
    return sorted(nums)


# ── 主入口 ────────────────────────────────────────────────

def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    ap = argparse.ArgumentParser(
        description="单块/批量译文合规校验（英译中专用）")
    ap.add_argument("-s", "--slug", required=True, help="书目 slug")
    chunk_group = ap.add_mutually_exclusive_group(required=True)
    chunk_group.add_argument("-c", "--chunk", type=int, help="单块块号")
    chunk_group.add_argument("--all", action="store_true", help="批量扫描所有已译块")
    ap.add_argument("-r", "--root", default=None, help="工作区根目录（缺省=脚本所在目录）")
    ap.add_argument("-a", "--assert", dest="must", default="", help="逗号分隔的'必须出现'串（仅单块）")
    ap.add_argument("-x", "--assert-absent", dest="must_not", default="", help="逗号分隔的'必须不出现'串（仅单块）")
    ap.add_argument("--diff", action="store_true", help="列出草稿→成品逐行差异")
    ap.add_argument("-t", "--target", default="final",
                    choices=["final", "review", "draft"],
                    help="校验哪个文件：final=成品(默认), review=审校稿, draft=草稿")
    args = ap.parse_args()

    root = Path(args.root) if args.root else Path(__file__).resolve().parent

    if args.all:
        chunks = find_chunks(root, args.slug, args.target)
        if not chunks:
            print(f"未找到 {args.slug} 的任何块（target={args.target}）")
            return 1
        print(f"===== 批量扫描: {args.slug}（{args.target}），共 {len(chunks)} 块 =====\n")
        total_fail = 0
        total_items = 0
        total_warn = 0
        for c in chunks:
            n, f, w, _ = verify_chunk(root, args.slug, c,
                                      must="", must_not="",
                                      show_diff=args.diff,
                                      target=args.target)
            if n < 0:
                total_fail += 1
            else:
                total_items += n
                total_fail += f
                total_warn += w
            print()
        print(f"===== 批量汇总: {len(chunks)} 块，{total_items} 项，"
              f"FAIL {total_fail}"
              + (f"，WARN {total_warn}（须逐条人工裁定，见各块明细）" if total_warn else "")
              + " =====")
        return 1 if total_fail else 0
    else:
        n, f, w, changed = verify_chunk(root, args.slug, args.chunk,
                                        must=args.must, must_not=args.must_not,
                                        show_diff=args.diff,
                                        target=args.target)
        if n < 0:
            return 1
        print(f"\n草稿→成品改动行数: {changed if changed >= 0 else 'N/A'}")
        return 1 if f else 0


if __name__ == "__main__":
    sys.exit(main())
