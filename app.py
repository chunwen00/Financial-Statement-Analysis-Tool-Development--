from __future__ import annotations

import json

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf

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

# ── 量化評分系統 ──────────────────────────────────────────────
# 每個指標依門檻給分(-2 最差 ~ +2 最佳)；分數越高越偏多(買進)。
# 正向指標(數值越高越好)：門檻為「>=」，由高到低判斷。
POSITIVE_SCORE_RULES = {
    "Gross_Margin": [(0.40, 2), (0.25, 1), (0.15, 0), (0.10, -1)],
    "Operating_Margin": [(0.20, 2), (0.10, 1), (0.05, 0), (0.00, -1)],
    "ROE": [(0.20, 2), (0.15, 1), (0.08, 0), (0.00, -1)],
    "EPS_Growth": [(0.20, 2), (0.05, 1), (-0.05, 0), (-0.20, -1)],
    "Revenue_YoY": [(0.15, 2), (0.05, 1), (-0.05, 0), (-0.15, -1)],
    "Current_Ratio": [(2.00, 2), (1.50, 1), (1.00, 0), (0.80, -1)],
}
# 反向指標(數值越低越好)：門檻為「<=」，由低到高判斷。
NEGATIVE_SCORE_RULES = {
    "Debt_Ratio": [(0.30, 2), (0.50, 1), (0.60, 0), (0.70, -1)],
    "PE": [(10.0, 2), (15.0, 1), (20.0, 0), (30.0, -1)],
}


def _score_positive(value: float, rules: list[tuple[float, int]]) -> int:
    for threshold, score in rules:
        if value >= threshold:
            return score
    return -2


def _score_negative(value: float, rules: list[tuple[float, int]]) -> int:
    for threshold, score in rules:
        if value <= threshold:
            return score
    return -2


def score_metrics(latest: pd.Series) -> dict:
    details: dict[str, int] = {}

    for col, rules in POSITIVE_SCORE_RULES.items():
        v = latest.get(col)
        if v is not None and not pd.isna(v):
            details[col] = _score_positive(float(v), rules)

    for col, rules in NEGATIVE_SCORE_RULES.items():
        v = latest.get(col)
        if v is not None and not pd.isna(v):
            details[col] = _score_negative(float(v), rules)

    fcf = latest.get("Free_Cash_Flow")
    if fcf is not None and not pd.isna(fcf):
        details["Free_Cash_Flow"] = 1 if float(fcf) > 0 else -2

    total = sum(details.values())
    n = len(details)
    avg = total / n if n else 0.0

    # 積極型門檻：HOLD 區間較窄(平均分 -0.4 ~ 0.4)，讓買賣訊號更積極。
    if avg >= 0.6:
        signal = "BUY"
    elif avg <= -0.6:
        signal = "SELL"
    else:
        signal = "HOLD"

    return {"details": details, "total": total, "max": n * 2, "avg": round(avg, 3), "signal": signal}


AI_SYSTEM_PROMPT = (
    "你是一位精通台股的價值投資專家。你會收到一家公司近幾期的關鍵財務指標(含趨勢)，以及一份系統用量化門檻算出的評分。\n"
    "請分析財務體質，指出優點與潛在風險，並給出明確的投資操作建議。語氣要專業、客觀。\n"
    "\n"
    "量化評分門檻(每個指標 -2 ~ +2 分)：\n"
    "- 毛利率：>=40% 給 +2、>=25% +1、>=15% 0、>=10% -1、其餘 -2\n"
    "- 營業利益率：>=20% +2、>=10% +1、>=5% 0、>=0% -1、<0% -2\n"
    "- ROE：>=20% +2、>=15% +1、>=8% 0、>=0% -1、<0% -2\n"
    "- EPS成長率：>=20% +2、>=5% +1、>=-5% 0、>=-20% -1、其餘 -2\n"
    "- 營收年增率(YoY)：>=15% +2、>=5% +1、>=-5% 0、>=-15% -1、其餘 -2\n"
    "- 流動比率：>=2 +2、>=1.5 +1、>=1 0、>=0.8 -1、<0.8 -2\n"
    "- 負債比率：<=30% +2、<=50% +1、<=60% 0、<=70% -1、>70% -2\n"
    "- 本益比(PE)：<=10 +2、<=15 +1、<=20 0、<=30 -1、>30 -2\n"
    "- 自由現金流：為正 +1、為負 -2\n"
    "\n"
    "操作建議規則(積極型)：依各指標平均分數決定，平均分 >=0.4 → BUY、<=-0.4 → SELL、其餘 → HOLD。\n"
    "\n"
    "重要規則：\n"
    "1. 你必須明確在 BUY / HOLD / SELL 三者擇一，不可迴避，也不要因資訊不足就預設 HOLD。\n"
    "2. 原則上以系統量化訊號為主；若近期『趨勢方向』明顯與量化訊號相反(例如分數高但各項指標連續惡化)，可調整，但須明確說明理由。\n"
    "3. 理由需引用具體指標數值、其得分與趨勢。\n"
    "4. 最後務必輸出一行『信心分數：x/10』。\n"
)


def prepare_ai_request(metrics_df: pd.DataFrame) -> tuple[list[dict], dict]:
    api_key = st.session_state.get("openai_api_key", "")
    if not api_key:
        raise ValueError("請先在左側輸入 OpenAI API Key。")

    df = metrics_df.copy()
    df = df.sort_index()
    df = df.dropna(how="all")
    if df.empty:
        raise ValueError("指標表為空，無法產生 AI 分析。")

    recent = df.tail(4)
    latest_date = str(df.index[-1].date()) if isinstance(df.index, pd.DatetimeIndex) else str(df.index[-1])

    trend = {}
    for date, row in recent.iterrows():
        date_key = str(date.date()) if isinstance(df.index, pd.DatetimeIndex) else str(date)
        period = {}
        for k, v in row.to_dict().items():
            zh = SUMMARY_COL_ZH.get(k, k)
            if pd.isna(v):
                period[zh] = None
            elif isinstance(v, (int, float)):
                period[zh] = round(float(v), 6)
            else:
                period[zh] = str(v)
        trend[date_key] = period

    score_info = score_metrics(df.iloc[-1])
    score_zh = {SUMMARY_COL_ZH.get(k, k): v for k, v in score_info["details"].items()}
    score_summary = {
        "各指標得分": score_zh,
        "總分": score_info["total"],
        "滿分": score_info["max"],
        "平均分": score_info["avg"],
        "系統量化訊號": score_info["signal"],
    }

    user_prompt = (
        f"以下是公司近 {len(recent)} 期的關鍵財務指標(由舊到新，最新一期為 {latest_date})，請特別觀察各指標的趨勢方向。\n"
        f"請依價值投資觀點，給出：\n"
        f"1) 財務體質總評\n"
        f"2) 優點(條列)\n"
        f"3) 風險(條列)\n"
        f"4) 操作建議：請在 BUY / HOLD / SELL 三選一(必須明確選邊，原則上以系統量化訊號為主)\n"
        f"5) 理由(條列，需引用具體指標數值、得分與趨勢)\n"
        f"6) 信心分數：x/10\n\n"
        f"系統量化評分(最新一期)：\n{json.dumps(score_summary, ensure_ascii=False, indent=2)}\n\n"
        f"近期指標趨勢(JSON)：\n{json.dumps(trend, ensure_ascii=False, indent=2)}\n"
    )

    messages = [
        {"role": "system", "content": AI_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
    return messages, score_info


def stream_ai_advice(messages: list[dict]):
    api_key = st.session_state.get("openai_api_key", "")
    if not api_key:
        raise ValueError("請先在左側輸入 OpenAI API Key。")

    try:
        from openai import OpenAI  # type: ignore
    except Exception as e:
        raise RuntimeError("找不到 openai 套件，請先安裝：pip install openai") from e

    client = OpenAI(api_key=api_key)

    # 串流輸出：邊生成邊顯示，縮短等待感並加速首字出現。
    stream = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        temperature=0.6,
        stream=True,
    )
    for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta


# 常見台股代碼 → 中文名稱對照(查不到時才以 yfinance 英文名遞補)。
TW_STOCK_NAMES = {
    "2330": "台積電", "2317": "鴻海", "2454": "聯發科", "2308": "台達電", "2303": "聯電",
    "2412": "中華電", "3711": "日月光投控", "2891": "中信金", "2882": "國泰金", "2881": "富邦金",
    "2886": "兆豐金", "2884": "玉山金", "2885": "元大金", "2887": "台新金", "2890": "永豐金",
    "2892": "第一金", "2880": "華南金", "2883": "開發金", "2888": "新光金", "5880": "合庫金",
    "1301": "台塑", "1303": "南亞", "1326": "台化", "6505": "台塑化", "2002": "中鋼",
    "2207": "和泰車", "2105": "正新", "2603": "長榮", "2609": "陽明", "2615": "萬海",
    "2618": "長榮航", "2610": "華航", "3008": "大立光", "2379": "瑞昱", "3034": "聯詠",
    "2357": "華碩", "2382": "廣達", "2395": "研華", "2376": "技嘉", "2474": "可成",
    "3045": "台灣大", "4904": "遠傳", "1216": "統一", "1101": "台泥", "1102": "亞泥",
    "2912": "統一超", "9910": "豐泰", "2327": "國巨", "2409": "友達", "3481": "群創",
    "2344": "華邦電", "2408": "南亞科", "2301": "光寶科", "6415": "矽力-KY", "8046": "南電",
    "3037": "欣興", "2492": "華新科", "1590": "亞德客-KY", "9904": "寶成", "5871": "中租-KY",
    "6669": "緯穎", "3661": "世芯-KY", "4938": "和碩", "2356": "英業達", "2353": "宏碁",
    "6770": "力積電", "3017": "奇鋐", "3231": "緯創", "2345": "智邦",
    "2801": "彰銀", "2823": "中壽", "2834": "臺企銀", "5876": "上海商銀",
}


@st.cache_data(show_spinner=False, ttl=24 * 3600)
def fetch_twse_names() -> dict[str, str]:
    """從證交所 ISIN 清單抓取上市/上櫃股票的『代碼 → 中文名稱』對照。"""
    try:
        import re

        import requests
    except Exception:
        return {}

    mapping: dict[str, str] = {}
    # strMode=2：上市；strMode=4：上櫃
    urls = [
        "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2",
        "https://isin.twse.com.tw/isin/C_public.jsp?strMode=4",
    ]
    headers = {"User-Agent": "Mozilla/5.0"}
    # 第一欄格式為『>2330　台積電<』：以全形空白分隔代號與名稱。
    pattern = re.compile(r">(\d{4,7})\u3000([^<]+?)<")

    for url in urls:
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            resp.encoding = "big5"
            for code, name in pattern.findall(resp.text):
                mapping[code] = name.strip()
        except Exception:
            continue

    return mapping


@st.cache_data(show_spinner=False)
def get_stock_name(stock_id: str) -> str | None:
    code = stock_id[:-3] if stock_id.endswith(".TW") else stock_id

    # 1) 優先使用證交所自動清單(涵蓋全部上市櫃)
    twse = fetch_twse_names()
    if code in twse:
        return twse[code]

    # 2) 證交所抓取失敗時，使用內建常見對照表
    zh = TW_STOCK_NAMES.get(code)
    if zh:
        return zh

    # 3) 最後以 yfinance 英文名遞補
    symbol = f"{code}.TW"
    try:
        info = yf.Ticker(symbol).info or {}
        return info.get("longName") or info.get("shortName")
    except Exception:
        return None


@st.cache_data(show_spinner=False)
def load_and_analyze(stock_id: str) -> tuple[pd.DataFrame, dict[str, pd.DataFrame], float | None, str | None]:
    data = get_financials(stock_id)
    analyzer = FinancialAnalyzer(
        data["income_statement"],
        data["balance_sheet"],
        data["cash_flow"],
        stock_id=stock_id,
    )
    summary_df = analyzer.summary()
    stock_name = get_stock_name(stock_id)
    return summary_df, data, analyzer.current_price, stock_name


with st.sidebar:
    st.subheader("輸入")
    stock_id = st.text_input("台股代碼（例如：2330）", value="2330").strip()
    st.text_input("OpenAI API Key", key="openai_api_key", type="password", placeholder="sk-...")
    run = st.button("分析", type="primary", use_container_width=True)


if "analysis" not in st.session_state:
    st.session_state["analysis"] = None


if run:
    with st.spinner("正在抓取財報並計算指標..."):
        summary_df, raw, current_price, stock_name = load_and_analyze(stock_id)
    st.session_state["analysis"] = {
        "stock_id": stock_id,
        "stock_name": stock_name,
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
    stock_name = analysis.get("stock_name")

    symbol = sid if sid.endswith(".TW") else sid + ".TW"
    if stock_name:
        st.subheader(f"{stock_name}（{symbol}）")
    else:
        st.subheader(symbol)
    st.caption(f"股票代碼：{symbol}；公司名稱：{stock_name or '—'}；目前股價（估）：{current_price}")

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
        try:
            with st.spinner("準備量化評分..."):
                messages, score_info = prepare_ai_request(summary_df)

            if score_info:
                signal = score_info["signal"]
                signal_zh = {"BUY": "買進", "HOLD": "持有", "SELL": "賣出"}.get(signal, signal)
                sc1, sc2, sc3 = st.columns(3)
                sc1.metric("系統量化訊號", f"{signal}（{signal_zh}）")
                sc2.metric("總分", f"{score_info['total']} / {score_info['max']}")
                sc3.metric("平均分", score_info["avg"])

                score_table = pd.DataFrame(
                    {"得分": {SUMMARY_COL_ZH.get(k, k): v for k, v in score_info["details"].items()}}
                )
                st.dataframe(score_table, use_container_width=True)

            # 串流顯示 AI 報告：逐字輸出，首字更快、整體等待感更短。
            st.write_stream(stream_ai_advice(messages))
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

