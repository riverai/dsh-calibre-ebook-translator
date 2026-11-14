#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
export-full.py — 全书导出工具

用途：将 translations/chunk-NNN.txt 按块号顺序拼接为单个 _full.txt，
      报告字符数、行数、缺失块。

用法：
    python export-full.py -s storyscience
    python export-full.py -s storyscience -o custom_name.txt
    python export-full.py -s storyscience --no-blank-between

参数：
    -s/--slug         书目 slug
    -r/--root         工作区根目录；缺省为脚本所在目录
    -o/--output       输出文件名（缺省 _full.txt，放在 translations/ 下）
    --no-blank-between  块间不加空行（默认每块之间加一个空行）

输出：
    translations/_full.txt（或指定文件名）
    控制台：总块数、总字符数、总行数、缺失块列表

退出码：0 = 成功；1 = 有缺失块（但仍生成部分输出）；2 = 参数错误
"""

import argparse
import sys
from pathlib import Path


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    ap = argparse.ArgumentParser(description="全书导出工具")
    ap.add_argument("-s", "--slug", required=True, help="书目 slug")
    ap.add_argument("-r", "--root", default=None, help="工作区根目录")
    ap.add_argument("-o", "--output", default="_full.txt", help="输出文件名")
    ap.add_argument("--no-blank-between", action="store_true",
                    help="块间不加空行（默认加一个空行）")
    args = ap.parse_args()

    root = Path(args.root) if args.root else Path(__file__).resolve().parent
    trans_dir = root / "books" / args.slug / "translations"
    if not trans_dir.is_dir():
        print(f"错误: 译文目录不存在: {trans_dir}")
        return 2

    # 发现所有 chunk-NNN.txt（排除 _full.txt 等非数字文件）
    chunks = []
    for f in trans_dir.iterdir():
        if f.name.startswith("chunk-") and f.suffix == ".txt":
            try:
                num = int(f.stem.split("-")[1])
                chunks.append((num, f))
            except ValueError:
                continue
    chunks.sort(key=lambda x: x[0])

    if not chunks:
        print(f"错误: 未找到任何 chunk-NNN.txt")
        return 2

    # 检测缺失块（序号不连续）
    max_num = chunks[-1][0]
    existing = {num for num, _ in chunks}
    missing = [i for i in range(max_num + 1) if i not in existing]

    # 拼接
    parts = []
    for num, f in chunks:
        text = f.read_text(encoding="utf-8")
        text = text.rstrip("\n")
        parts.append(text)

    separator = "" if args.no_blank_between else "\n"
    full = separator.join(parts) + "\n"

    out_path = trans_dir / args.output
    out_path.write_text(full, encoding="utf-8", newline="")

    # 报告
    print(f"导出完成: {out_path}")
    print(f"总块数: {len(chunks)}")
    print(f"总字符: {len(full):,}")
    print(f"总行数: {len(full.splitlines())}")
    if missing:
        print(f"缺失块: {missing}")
        return 1
    print("缺失块: 无")
    return 0


if __name__ == "__main__":
    sys.exit(main())
