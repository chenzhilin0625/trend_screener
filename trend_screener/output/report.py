"""
Markdown 报告生成器 —— 表格化详细指标
"""

from datetime import datetime
import os


class ReportGenerator:
    def __init__(self, output_dir="."):
        self.output_dir = output_dir

    def generate(self, market_result, industries, stocks):
        today = datetime.now().strftime("%Y-%m-%d")
        lines = []

        lines.append(f"# 趋势筛选报告 — {today}")
        lines.append("")
        lines.append(f"*自动生成于 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")
        lines.append("")

        # =====================
        #  大盘
        # =====================
        lines.append("## 一、大盘趋势评估")
        lines.append("")
        if market_result:
            lines.append(f"| 指标 | 数值 | 权重 |")
            lines.append(f"|---|---|---|")
            lines.append(f"| 综合评分 | **{market_result['score']:.2f}** "
                         f"({market_result['grade']}级) | - |")
            lines.append(f"| 建议 | {market_result['recommendation']} | - |")

            trend = market_result.get("trend")
            if trend:
                p = "↑" if trend["prim_up"] else "↓"
                s = "↑" if trend["sec_up"] else "↓"
                m = "↑" if trend["min_up"] else "↓"
                lines.append(f"| 趋势状态 | {trend['state']} | - |")
                lines.append(f"| 长期(周线) | {trend['primary_score']:.1f}/4 {p} | 50% |")
                lines.append(f"| 中期(日线) | {trend['secondary_score']:.1f}/4 {s} | 30% |")
                lines.append(f"| 短期(日线) | {trend['minor_score']:.1f}/3 {m} | 20% |")

            lines.append(f"| 市场宽度 | {market_result.get('breadth_score', 0):.2f} | 20% |")
            lines.append(f"| 量价配合 | {'Y' if market_result.get('vol_healthy') else 'N'} | 10% |")
            lines.append(f"| 多指数确认 | {'Y' if market_result.get('multi_index_ok') else 'N'} | 10% |")
        lines.append("")

        # =====================
        #  行业表格
        # =====================
        lines.append("## 二、行业趋势矩阵")
        lines.append("")
        if industries:
            lines.append("| # | 行业 | 总分 | 长 | 中 | 短 | RS | 趋势 | 回调 | 初现 | 震荡 | 过热 | 标签 |")
            lines.append("|---|------|------|----|----|----|------|------|------|------|------|------|------|")
            for i, ind in enumerate(industries[:20], 1):
                p = "↑" if ind["prim_up"] else "↓"
                s = "↑" if ind["sec_up"] else "↓"
                m = "↑" if ind["min_up"] else "↓"
                pb = "Y" if ind.get("is_pullback") else ""
                em = "Y" if ind.get("is_emergence") else ""
                rg = "Y" if ind.get("is_ranging") else ""
                ob = ind.get("ob_level", "")
                flags = " ".join(ind.get("labels", []))
                lines.append(
                    f"| {i} | {ind['name']} | {ind['total_score']:.3f} | "
                    f"{p} | {s} | {m} | "
                    f"{ind['rs_score']:.3f} | {ind['trend_state']} | "
                    f"{pb} | {em} | {rg} | {ob} | {flags} |"
                )

            lines.append("")
            # OB 明细子表
            lines.append("### 过热明细")
            lines.append("")
            ob_inds = [i for i in industries[:20] if i.get("ob_level") in ("过热", "严重过热", "偏高")]
            if ob_inds:
                lines.append("| # | 行业 | OB评分 | OB等级 | 警告 |")
                lines.append("|---|------|--------|--------|------|")
                for i, ind in enumerate(ob_inds, 1):
                    warns = ", ".join(ind.get("ob_warnings", []))
                    lines.append(f"| {i} | {ind['name']} | {ind.get('ob_score',0):.2f} | "
                                 f"{ind.get('ob_level','')} | {warns} |")
            else:
                lines.append("_无过热行业_")
        lines.append("")

        # =====================
        #  个股表格
        # =====================
        lines.append("## 三、个股趋势候选")
        lines.append("")
        if stocks:
            lines.append("| # | 代码 | 名称 | 行业 | 得分 | 通过 | 长 | 中 | 短 | ADX | 3TF | HH | EMA | ADXc | 60 | Vol | RS | 过热 | 状态 |")
            lines.append("|---|------|------|------|------|------|----|----|----|-----|-----|-----|-----|------|-----|-----|-----|------|------|")
            for i, s in enumerate(stocks[:25], 1):
                chk = s.get("checks", {})
                p = "↑" if s["long_up"] else "↓"
                m = "↑" if s["mid_up"] else "↓"
                n = "↑" if s["short_up"] else "↓"
                tf3 = "Y" if chk.get("三尺度趋势") else "N"
                hh = "Y" if chk.get("HH/HL结构") else "N"
                ema = "Y" if chk.get("均线排列") else "N"
                adxc = "Y" if chk.get("ADX强度") else "N"
                ma60 = "Y" if chk.get("站上MA60") else "N"
                vol = "Y" if chk.get("量价健康") else "N"
                rs = "Y" if chk.get("相对强度>1.0") else "N"
                ob = s.get("ob_level", "")
                ind = s.get("industry", "")
                lines.append(
                    f"| {i} | {s['code']} | {s['name']} | {ind} | "
                    f"{s['score']:.1f} | {s['passed']}/7 | "
                    f"{p} | {m} | {n} | {s['adx']:.1f} | "
                    f"{tf3} | {hh} | {ema} | {adxc} | {ma60} | {vol} | {rs} | "
                    f"{ob} | {s.get('trend_state', '')} |"
                )
        else:
            lines.append("_无符合条件的个股_")
        lines.append("")

        lines.append("---")
        lines.append(f"*报告由趋势筛选器自动生成*")

        # 写入文件
        filename = f"trend_report_{today}.md"
        filepath = os.path.join(self.output_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        return filepath


def generate_report(market_result, industries, stocks, output_dir="."):
    gen = ReportGenerator(output_dir)
    return gen.generate(market_result, industries, stocks)
