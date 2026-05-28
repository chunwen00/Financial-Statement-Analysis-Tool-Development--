from __future__ import annotations

import json

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from analyzer import FinancialAnalyzer
from data_loader import get_financials


st.set_page_config(page_title="台股財報分析工具", layout="wide")
st.title("台股財報分析工具（yfinance）")

SUMMARY_COL_ZH = {
    "Gross_Margin": "毛利率",
    "Operating_Margin": "營業利益率",
    "ROE": "ROE(股東權益報酬率)",
    "EPS_Growth": "EPS成長率",
    "Free_Cash_Flow": "自由現金流(FCF)",
    "PE": "本益比(PE)",
    "Debt_Ratio": "負債比率",
    "Current_Ratio": "流動比率",
    "Revenue_YoY": "營收年增率(YoY)",
}

STATEMENT_COL_ZH = {
    # Income statement (常用)
    "Total Revenue": "營收",
    "Operating Revenue": "營收(營業收入)",
    "Gross Profit": "毛利",
    "Operating Income": "營業利益",
    "Net Income": "淨利",
    "Net Income Common Stockholders": "歸屬母公司淨利",
    "Diluted EPS": "稀釋EPS",
    "Basic EPS": "基本EPS",
    # Balance sheet (常用)
    "Total Assets": "總資產",
    "Total Liabilities Net Minority Interest": "總負債(不含少數股權)",
    "Current Assets": "流動資產",
    "Current Liabilities": "流動負債",
    "Stockholders Equity": "股東權益",
    "Total Equity Gross Minority Interest": "權益總額(含少數股權)",
    # Cash flow (常用)
    "Free Cash Flow": "自由現金流(FCF)",
    "Operating Cash Flow": "營業現金流",
    "Total Cash From Operating Activities": "營業活動現金流入(出)",
    "Capital Expenditures": "資本支出(CapEx)",
}

AI_SYSTEM_PROMPT = (
    "你是一位精通台股的價值投資專家，請分析這家公司的財務體質，指出優點與潛在風險，並給予投資操作建議。語氣要專業、客觀。"
)


def get_ai_advice(metrics_df: pd.DataFrame) -> tuple[str, dict | None]:
    api_key = st.session_state.get("openai_api_key", "")
    if not api_key:
        raise ValueError("請先在左側輸入 OpenAI API Key。")

    df = metrics_df.copy()
    df = df.sort_index()
    df = df.dropna(how="all")
    if df.empty:
        raise ValueError("指標表為空，無法產生 AI 分析。")

    latest = df.iloc[-1]
    latest_date = str(df.index[-1].date()) if isinstance(df.index, pd.DatetimeIndex) else str(df.index[-1])

    payload = {}
    for k, v in latest.to_dict().items():
        if pd.isna(v):
            payload[k] = None
        elif isinstance(v, (int, float)):
            payload[k] = float(v)
        else:
            payload[k] = str(v)

    metrics_zh = {SUMMARY_COL_ZH.get(k, k): v for k, v in payload.items()}

    user_prompt = (
        f"以下是公司最新一季(或最新一期)的關鍵財務指標，日期：{latest_date}\n"
        f"請依價值投資觀點，給出：\n"
        f"1) 財務體質總評\n"
        f"2) 優點(條列)\n"
        f"3) 風險(條列)\n"
        f"4) 操作建議：請在 BUY / HOLD / SELL 三選一\n"
        f"5) 理由(條列)\n\n"
        f"指標(JSON)：\n{json.dumps(metrics_zh, ensure_ascii=False, indent=2)}\n"
    )

    try:
        from openai import OpenAI  # type: ignore
    except Exception as e:
        raise RuntimeError("找不到 openai 套件，請先安裝：pip install openai") from e

    client = OpenAI(api_key=api_key)

    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": AI_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.4,
    )

    text = (resp.choices[0].message.content or "").strip()
    return text, None


@st.cache_data(show_spinner=False)
def load_and_analyze(stock_id: str) -> tuple[pd.DataFrame, dict[str, pd.DataFrame], float | None]:
    data = get_financials(stock_id)
    analyzer = FinancialAnalyzer(
        data["income_statement"],
        data["balance_sheet"],
        data["cash_flow"],
        stock_id=stock_id,
    )
    summary_df = analyzer.summary()
    return summary_df, data, analyzer.current_price


with st.sidebar:
    st.subheader("輸入")
    stock_id = st.text_input("台股代碼（例如：2330）", value="2330").strip()
    st.text_input("OpenAI API Key", key="openai_api_key", type="password", placeholder="sk-...")
    run = st.button("分析", type="primary", use_container_width=True)


if "analysis" not in st.session_state:
    st.session_state["analysis"] = None


if run:
    with st.spinner("正在抓取財報並計算指標..."):
        summary_df, raw, current_price = load_and_analyze(stock_id)
    st.session_state["analysis"] = {
        "stock_id": stock_id,
        "summary_df": summary_df,
        "raw": raw,
        "current_price": current_price,
    }

analysis = st.session_state.get("analysis")

if analysis:
    summary_df = analysis["summary_df"]
    raw = analysis["raw"]
    current_price = analysis["current_price"]
    sid = analysis["stock_id"]

    st.caption(f"股票代碼：{sid if sid.endswith('.TW') else sid + '.TW'}；目前股價（估）：{current_price}")

    if summary_df is None or summary_df.empty:
        st.error("查無財報資料，請確認代碼是否正確或稍後再試。")
        st.stop()

    summary_df = summary_df.sort_index()

    last4 = summary_df.tail(4)
    last4_zh = last4.rename(columns=SUMMARY_COL_ZH)

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("近四季毛利率與營業利益率趨勢")
        fig = go.Figure()
        fig.add_trace(
            go.Scatter(x=last4_zh.index, y=last4_zh[SUMMARY_COL_ZH["Gross_Margin"]], mode="lines+markers", name="毛利率")
        )
        fig.add_trace(
            go.Scatter(
                x=last4_zh.index,
                y=last4_zh[SUMMARY_COL_ZH["Operating_Margin"]],
                mode="lines+markers",
                name="營業利益率",
            )
        )
        fig.update_layout(
            xaxis_title="日期",
            yaxis_title="比率",
            yaxis_tickformat=".0%",
            legend_title_text="",
            margin=dict(l=10, r=10, t=10, b=10),
        )
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("股東權益報酬率 (ROE) 走勢")
        fig2 = go.Figure()
        fig2.add_trace(
            go.Scatter(
                x=last4_zh.index,
                y=last4_zh[SUMMARY_COL_ZH["ROE"]],
                mode="lines+markers",
                name="ROE",
            )
        )
        fig2.update_layout(
            xaxis_title="日期",
            yaxis_title="ROE",
            yaxis_tickformat=".0%",
            legend_title_text="",
            margin=dict(l=10, r=10, t=10, b=10),
        )
        st.plotly_chart(fig2, use_container_width=True)

    st.subheader("關鍵財務指標彙整表")
    display_df = summary_df.rename(columns=SUMMARY_COL_ZH).copy()
    for c in ["Gross_Margin", "Operating_Margin", "ROE", "EPS_Growth", "Debt_Ratio", "Current_Ratio", "Revenue_YoY"]:
        zh = SUMMARY_COL_ZH.get(c)
        if zh and zh in display_df.columns:
            display_df[zh] = display_df[zh].astype("float64")
    st.dataframe(display_df.sort_index(ascending=False), use_container_width=True)

    st.subheader("AI 診斷報告")
    gen = st.button("生成 AI 診斷報告", type="secondary", key="gen_ai_report")
    if gen:
        with st.spinner("AI 生成中..."):
            try:
                report, _ = get_ai_advice(summary_df)
                st.markdown(report)
            except Exception as e:
                st.error(str(e))

    with st.expander("原始三大報表（可選）"):
        st.write("損益表")
        st.dataframe(
            raw["income_statement"].rename(columns=STATEMENT_COL_ZH).sort_index(ascending=False),
            use_container_width=True,
        )
        st.write("資產負債表")
        st.dataframe(
            raw["balance_sheet"].rename(columns=STATEMENT_COL_ZH).sort_index(ascending=False),
            use_container_width=True,
        )
        st.write("現金流量表")
        st.dataframe(
            raw["cash_flow"].rename(columns=STATEMENT_COL_ZH).sort_index(ascending=False),
            use_container_width=True,
        )

else:
    st.info("在左側輸入台股代碼後按「分析」。")

