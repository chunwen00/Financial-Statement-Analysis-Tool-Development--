"""data_loader.py：使用 yfinance 載入台股財報資料。"""  # 模組說明（含用途）  
  
from __future__ import annotations  # 啟用較新的型別註記行為（避免前置宣告問題）  
  
from typing import Dict  # 匯入 Dict 型別（用於回傳結構）  
  
import pandas as pd  # 匯入 pandas（用於 DataFrame 整理）  
import yfinance as yf  # 匯入 yfinance（作為財報資料來源）  
  
  
def _to_date_index(df: pd.DataFrame) -> pd.DataFrame:  # 定義輔助函數：把 yfinance 財報表轉成「日期索引」的 DataFrame  
    if df is None or df.empty:  # 若來源為空（沒資料或抓取失敗），直接回傳空表  
        return pd.DataFrame()  # 回傳空的 DataFrame（避免後續處理出錯）  
  
    out = df.copy()  # 複製一份避免修改到原始 DataFrame  
    out = out.T  # yfinance 財報通常「欄是日期、列是科目」；轉置後變成「列是日期」  
    out.index = pd.to_datetime(out.index, errors="coerce")  # 將索引轉成 datetime（確保 Index 是日期型別）  
    out = out.sort_index()  # 依日期由舊到新排序（便於時間序分析）  
    out = out.loc[~out.index.isna()]  # 移除無法轉成日期的索引列（避免 NaT 影響）  
    out.index.name = "Date"  # 設定索引名稱為 Date（可讀性更好）  
    return out  # 回傳整理完成的 DataFrame  
  
  
def get_financials(stock_id: str) -> Dict[str, pd.DataFrame]:  # 取得損益表/資產負債表/現金流量表（回傳 DataFrame 字典）  
    ticker_symbol = stock_id if stock_id.endswith(".TW") else f"{stock_id}.TW"  # 台股代號補上 .TW（如 2330 -> 2330.TW）  
    ticker = yf.Ticker(ticker_symbol)  # 建立 yfinance 的 Ticker 物件（用於抓取財報）  
  
    income_stmt_raw = getattr(ticker, "financials", pd.DataFrame())  # 抓「損益表（年）」；若不存在則用空表  
    balance_sheet_raw = getattr(ticker, "balance_sheet", pd.DataFrame())  # 抓「資產負債表（年）」；若不存在則用空表  
    cash_flow_raw = getattr(ticker, "cashflow", pd.DataFrame())  # 抓「現金流量表（年）」；若不存在則用空表  
  
    income_statement = _to_date_index(income_stmt_raw)  # 整理損益表為「日期索引」格式  
    balance_sheet = _to_date_index(balance_sheet_raw)  # 整理資產負債表為「日期索引」格式  
    cash_flow = _to_date_index(cash_flow_raw)  # 整理現金流量表為「日期索引」格式  
  
    return {  # 回傳三張表（用 key 區分）  
        "income_statement": income_statement,  # 損益表（Income Statement）  
        "balance_sheet": balance_sheet,  # 資產負債表（Balance Sheet）  
        "cash_flow": cash_flow,  # 現金流量表（Cash Flow）  
    }  # 結束回傳字典  
from data_loader import get_financials
from analyzer import FinancialAnalyzer

d = get_financials("2330")  # 或 "2330.TW"
analyzer = FinancialAnalyzer(d["income_statement"], d["balance_sheet"], d["cash_flow"])
summary_df = analyzer.summary()

print(summary_df)