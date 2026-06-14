from __future__ import annotations

import argparse
from pathlib import Path

from .pipeline import run_analysis


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="中文 A 股多维研究工具")
    parser.add_argument("request", nargs="+", help="自然语言请求，例如：/股票 分析 600519.SH")
    parser.add_argument("--out-dir", default="output", help="输出目录，默认 output")
    args = parser.parse_args(argv)
    text = " ".join(args.request)
    try:
        result = run_analysis(text, Path(args.out_dir))
    except Exception as exc:
        print(f"FAIL {exc}")
        return 1
    print(_summary(result))
    return 0


def _summary(result: dict) -> str:
    lines = ["## 核心结论", ""]
    for item in result["results"]:
        sc = item["scorecard"]
        meta = (item.get("pack") or {}).get("meta") or {}
        name = meta.get("name")
        display_name = f"{name}（{sc['symbol']}）" if name else sc["symbol"]
        lines.append(f"- **股票**：{display_name}")
        lines.append(f"- **数据日期**：{sc['trade_date']}")
        lines.append(f"- **综合评级**：{sc.get('rating_label') or sc['rating']}")
        lines.append(f"- **综合分数**：{sc['scores']['total']}/100")
        lines.append(f"- **详细报告**：`{item['report_path']}`")
        lines.append("")
    return "\n".join(lines).strip()


if __name__ == "__main__":
    raise SystemExit(main())
