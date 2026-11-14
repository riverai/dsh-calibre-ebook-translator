#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
apply-edits.py — 精确编辑工具（唯一性断言 + 批量替换）

用途：给定一个目标文件和一份编辑清单（TSV），先对每条编辑做唯一性预检
     （旧串在文件中恰好出现 1 次），全部通过后批量替换并写回。
      避免使用 edit 工具时每次编辑后都需要 re-read 的开销和 token 浪费。

用法：
    python apply-edits.py <target_file> <edits_tsv>      # TSV 批量精确编辑（唯一性断言）
    python apply-edits.py <target_file> --fix-quotes     # ASCII 双引号 → 全角 “ ”
    （--fix-quotes 只动 ASCII 双引号，保留英文撇号如 Swann's Way；引号嵌套请用 TSV 逐条处理）

编辑清单格式（TSV，制表符分隔，UTF-8）：
    旧串	新串	说明	[出现次序]
    旧串	新串	说明	[出现次序]
    ...

    · 每行一个编辑，用制表符（\\t）分隔
    · 空行和以 # 开头的行忽略
    · "说明"列仅用于日志输出，不参与匹配
    · 旧串和新串都可以包含中文、标点等任意 UTF-8 字符（不能含换行，TSV 按行切分）
    · 【第 4 列·可选】出现次序：
         留空      = 旧串必须恰好出现 1 次（默认，最严格）
         all       = 旧串出现几次就替换几次（用于"同一行在文件里重复出现、
                     且每一处都需要同样修改"的情形，如目录页重复列出同一章标题）
         数字 k    = 只替换第 k 次出现（用于同一行重复但只需改其中一处的罕见情形）
      留空之外的取值会跳过"恰好 1 次"的唯一性要求，但会改用对应的计数要求校验；
      批内冲突预检也会相应放宽（相同旧串只要次序不同/含 all 即视为合法）。

安全机制：
    1) 唯一性预检：每条旧串在目标文件中必须恰好出现 1 次，否则拒绝全部修改
    2) 【批内冲突预检】批内两条旧串完全相同、或一条是另一条的子串 → 拒绝整批。
       理由见下方『同批顺序陷阱』——这是本项目踩过的真实坑。
    3) 应用时**逐条断言**：每条替换前再核一次"旧串恰好出现 1 次"，不满足立即中止，
       全程只在内存中进行，未通过则不写文件。杜绝"静默变成空操作却报告已应用"。
    4) 预检通过后才应用替换，写回文件
    5) 写回后自动回读，打印改动行数，供人工确认
    6) 如果任何一条预检失败，**不做任何修改**（整批回滚），以非零退出码结束

⚠ 同批顺序陷阱（本项目实战教训，构造 TSV 前必读）：
    预检是拿【原始文本】为基准、对每条独立计数的，所以两条 old_string 相同的编辑
    会双双报 OK；但应用是顺序进行的——第一条把该区域改写后，第二条的 old_string
    已不复存在，`str.replace` 会**静默返回原文本**（不报错）。
    结果：编辑清单显示"已应用"，实际却是空操作，成品只落地了一半。
    真实事故：2026-11-11 在 statusgame 上，chunk 074/131/135/137 共 6 条编辑被吞，
    其中 chunk-135 L5 的"排名与淘汰→评级淘汰"整条消失，直到全书扫描才被发现。
    典型触发写法（生成 TSV 的辅助脚本里很常见）：
        rep(5, "小A", "小A改")      # 两条 old_string 都是"第 5 行整行" → 必吞一条
        rep(5, "小B", "小B改")
    【正确做法】同一行有多处要改时，先把它们串成一次替换，只产出**一条**编辑：
        old = lines[i-1]
        new = old.replace("小A","小A改").replace("小B","小B改")
    （本工具现在会在预检阶段直接拦住这种清单，不再让它悄悄吞掉编辑。）

⚠ 引号形态陷阱（本项目实战教训，构造 TSV 前必读）：
    肉眼相同形态的引号，字节上可能不同：
        "  U+0022  ASCII 直双引号        “ ”  U+201C/U+201D  全角双引号（有开/关方向）
        '  U+0027  ASCII 直单引号/撇号   ‘ ’  U+2018/U+2019  全角单引号
    常见触发场景：
    ① 对目标文件跑过 --fix-quotes 之后，文件里的 ASCII 双引号已变全角；
       若凭记忆（而非实读文件）构造 TSV 旧串，预检必然 count=0。
    ② 嵌套引号串（如 “‘…“…”…’”）中，全角双引号有开/关方向之分
       （“ 左开 / ” 右关），手打极易方向颠倒。
    ③ 用某些工具写 TSV 时文件头可能被加上 UTF-8 BOM（EF BB BF），
       导致第一行旧串永远匹配失败。
    本工具会自动剥除 BOM 与行尾 \r，但无法自动纠正引号形态。
    【可靠做法】构造含引号的 TSV 时：
    - 先用 read 工具实读目标文件，从读取结果中逐字节复制旧串；或
    - 用 Python 按 Unicode 码位构造（chr(0x201C) 等），勿凭记忆手打。
    预检失败（整批回滚）时的处理纪律：
    - 退出码=1；输出末尾有 FATAL 行，不可忽略；
    - 拆分重试时必须对照原裁定清单【逐条清点】，禁止只补报错行
      （实战中曾因只补报错行漏掉 10 条，导致成品短暂回退为旧文本）。

适用场景（翻译工作流）：
    · 在 temptranslations/chunk-NNN.review.txt 上批量应用审校采纳的修复
    · 在 translations/chunk-NNN.txt 上做回改
    · 任何需要"只改该改的行，其余逐字不变"的精确编辑场景

退出码：
    0 = 全部成功
    1 = 预检失败（未修改文件；stdout 末尾输出 FATAL: BATCH ROLLED BACK）
    2 = 参数错误 / 文件缺失
"""
import sys
from pathlib import Path


def load_edits(tsv_path: Path) -> list[tuple[str, str, str]]:
    """读取 TSV 编辑清单，返回 [(旧串, 新串, 说明), ...]。

    自动剥除 UTF-8 BOM（用 utf-8-sig 读取）与行尾 \\r（CRLF 残留），
    否则首行旧串 / 各行末列会带隐藏字节，导致预检必然 count=0。
    """
    raw_text = tsv_path.read_text(encoding="utf-8-sig")  # utf-8-sig 自动去 BOM
    edits = []
    for raw in raw_text.splitlines():
        line = raw.rstrip("\r")
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 2:
            print(f"  警告: 跳过格式不正确的行（列数<2）: {line[:60]}...", file=sys.stderr)
            continue
        old = parts[0]
        new = parts[1]
        note = parts[2].rstrip("\r") if len(parts) > 2 else ""
        occ = parts[3].strip().lower() if len(parts) > 3 else ""
        if occ and occ != "all":
            try:
                occ = str(int(occ))
            except ValueError:
                print(f"  警告: 第 4 列（出现次序）无法识别，改按默认处理: {occ!r}",
                      file=sys.stderr)
                occ = ""
        edits.append((old, new, note, occ))
    return edits


def find_all(text: str, sub: str) -> list:
    """返回 sub 在 text 中所有不重叠出现的起始偏移。"""
    out, start = [], 0
    while True:
        i = text.find(sub, start)
        if i < 0:
            return out
        out.append(i)
        start = i + len(sub)


def apply_one(text: str, old: str, new: str, occ: str) -> tuple:
    """按出现次序应用一条编辑，返回 (新文本, 实际替换次数)。

    occ=="" → 只替换唯一那一处；"all" → 全部；数字 → 只替换第 k 处。
    用偏移拼接而非 str.replace，避免 order-of-application 造成的索引漂移。
    """
    offs = find_all(text, old)
    if occ == "all":
        return text.replace(old, new), len(offs)
    k = int(occ) if occ else 1          # 留空 = 唯一那一处（预检已保证恰好 1 次）
    i = offs[k - 1]
    return text[:i] + new + text[i + len(old):], 1


def fix_quotes(text: str) -> tuple[str, int, int]:
    """把 ASCII 双引号按‘开/关’交替转为全角 “ ”，返回 (新文本, 转换数, 剩余数)。

    说明：只处理 ASCII 双引号 (U+0022)。ASCII 单引号不做全局转换
    （英文书名/所有格如 Swann's Way 须保留 ASCII 撇号）；引号嵌套场景
    请用 TSV 逐条精确处理。
    """
    out_lines = []
    n = 0
    for ln in text.split("\n"):
        buf, opener = [], True
        for ch in ln:
            if ch == "\u0022":
                buf.append("\u201c" if opener else "\u201d")
                opener = not opener
                n += 1
            else:
                buf.append(ch)
        out_lines.append("".join(buf))
    new = "\n".join(out_lines)
    return new, n, new.count("\u0022")


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    # 用法 1: python apply-edits.py <target_file> <edits_tsv>
    # 用法 2: python apply-edits.py <target_file> --fix-quotes
    if len(sys.argv) != 3:
        print("用法:")
        print("  python apply-edits.py <target_file> <edits_tsv>")
        print("  python apply-edits.py <target_file> --fix-quotes")
        return 2

    target = Path(sys.argv[1])
    arg2 = sys.argv[2]

    if not target.is_file():
        print(f"错误: 目标文件不存在: {target}")
        return 2

    # ── 模式：ASCII 双引号 → 全角 ──
    if arg2 == "--fix-quotes":
        t = target.read_text(encoding="utf-8")
        before = t.count("\u0022")
        if before == 0:
            print(f"{target.name}: 无 ASCII 双引号，无需处理。")
            return 0
        new, n, left = fix_quotes(t)
        print(f"=== 引号转换：{target.name} ===")
        print(f"  转换前 ASCII 双引号: {before}")
        print(f"  已转换: {n}    转换后剩余: {left}")
        if left:
            print("  警告: 仍有 ASCII 双引号残留（引号不成对？），请人工核对。")
        target.write_text(new, encoding="utf-8", newline="")
        lines = target.read_text(encoding="utf-8").splitlines()
        print(f"  已写回，行数={len(lines)}")
        return 0

    # ── 模式：TSV 批量精确编辑 ──
    tsv = Path(arg2)
    if not tsv.is_file():
        print(f"错误: 编辑清单不存在: {tsv}")
        return 2

    edits = load_edits(tsv)
    if not edits:
        print("编辑清单为空，无操作。")
        return 0

    t = target.read_text(encoding="utf-8")

    # ── 唯一性预检 ──
    print("=== 唯一性预检 ===")
    ok = True
    n_missing = 0   # count=0：旧串不存在（多为引号形态/编码不匹配）
    n_dupe = 0      # count>1：旧串不唯一（需加长锚点）
    for i, (old, new, note, occ) in enumerate(edits, 1):
        n = t.count(old)
        if occ == "":
            if n == 1:
                flag = "OK"
            elif n == 0:
                flag = "!!! count=0 旧串不存在"
                n_missing += 1
                ok = False
            else:
                flag = f"!!! count={n} 旧串不唯一（可加第 4 列 all/k 指定次序）"
                n_dupe += 1
                ok = False
        elif occ == "all":
            if n >= 1:
                flag = f"OK(全部 {n} 处)"
            else:
                flag = "!!! count=0 旧串不存在"
                n_missing += 1
                ok = False
        else:
            k = int(occ)
            if n >= k:
                flag = f"OK(第 {k}/{n} 处)"
            else:
                flag = f"!!! 要求第 {k} 处，但只找到 {n} 处"
                n_missing += 1
                ok = False
        print(f"  [{flag}] #{i} {note}")

    # ── 批内冲突预检（防止同批顺序陷阱静默吞掉编辑）──
    exact_dupes, overlaps = [], []
    for i in range(len(edits)):
        for j in range(i + 1, len(edits)):
            oi, oj = edits[i][0], edits[j][0]
            ci, cj = edits[i][3], edits[j][3]
            if oi == oj:
                # 第 4 列（all / k）能区分时视为合法，其余情况仍是静默吞编辑的隐患
                distinguishable = (ci != cj and ci != "" and cj != "")
                if not distinguishable:
                    exact_dupes.append((i + 1, j + 1, oi))
            elif oi in oj or oj in oi:
                short, long_ = (i + 1, j + 1) if len(oi) <= len(oj) else (j + 1, i + 1)
                overlaps.append((short, long_,
                                 oi if len(oi) <= len(oj) else oj))
    if exact_dupes or overlaps:
        print("\n=== 批内冲突预检 ===")
        for a, b, s in exact_dupes:
            print(f"  [!!! 批内重复] #{a} 与 #{b} 的旧串完全相同: {s[:50]}...")
        for a, b, s in overlaps:
            print(f"  [!!! 批内包含] #{a} 的旧串是 #{b} 旧串的子串: {s[:50]}...")
        print("  原因：预检按原始文本逐条计数（都通过），但应用是顺序的——")
        print("        先应用的那条会改写区域，后一条的旧串便不复存在，")
        print("        str.replace 静默返回原文本，编辑被吞却仍报告'已应用'。")
        print("  修法：同一行/同一区域的多处修改请串成【一条】编辑"
              "（old 取整行，new 为链式 replace 的结果）。")
        ok = False

    if not ok:
        print("\n预检未通过，未做任何修改（整批回滚，文件未被触碰）。")
        if n_missing:
            print(f"  · {n_missing} 条旧串 count=0：多半是引号形态（\" vs “” / ' vs ‘’）"
                  f"或隐藏字节不匹配——请实读目标文件逐字节复制旧串，"
                  f"或用 chr(0x201C) 等码位构造（详见文件头『引号形态陷阱』）。")
        if n_dupe:
            print(f"  · {n_dupe} 条旧串不唯一：请在旧串中加入前后文加长锚点。")
        if exact_dupes or overlaps:
            print(f"  · 批内冲突 {len(exact_dupes) + len(overlaps)} 组："
                  f"合并为整行单条编辑后重试（详见文件头『同批顺序陷阱』）。")
        print("\nFATAL: BATCH ROLLED BACK — 重试时必须对照原清单逐条清点，"
              "禁止只补报错行（易漏改，详见文件头说明）。")
        return 1

    # ── 应用替换（逐条断言，绝不静默空操作）──
    print("\n=== 应用修改 ===")
    total_reps = 0
    for i, (old, new, note, occ) in enumerate(edits, 1):
        cnt = t.count(old)
        if occ == "":
            need_ok = (cnt == 1)
            expect = "1 次"
        elif occ == "all":
            need_ok = (cnt >= 1)
            expect = "至少 1 次"
        else:
            need_ok = (cnt >= int(occ))
            expect = f"至少 {occ} 次"
        if not need_ok:
            print(f"  !!! 中止：第 #{i} 条在应用阶段旧串出现 {cnt} 次"
                  f"（预期{expect}）——已被前序编辑改动，文件未写入。")
            print("\nFATAL: BATCH ABORTED — 文件未被触碰；"
                  "请把互相影响的多处修改合并为整行单条编辑，"
                  "或用第 4 列（all / 次序）显式指定。")
            return 1
        t, reps = apply_one(t, old, new, occ)
        total_reps += reps
        print(f"  已应用: {note}" + (f"（替换 {reps} 处）" if reps != 1 else ""))
    print(f"  合计替换 {total_reps} 处")

    target.write_text(t, encoding="utf-8", newline="")

    # ── 回读确认 ──
    lines = target.read_text(encoding="utf-8").splitlines()
    print(f"\n已写回 {target.name}，行数={len(lines)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
