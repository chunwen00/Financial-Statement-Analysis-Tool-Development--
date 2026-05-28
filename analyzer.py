"""analyzer.py：計算台股財務指標（輸入為三大報表 DataFrame）。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

import numpy as np
import pandas as pd
import yfinance as yf


def _ensure_datetime_index(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()
    if not isinstance(out.index, pd.DatetimeIndex):
        out.index = pd.to_datetime(out.index, errors="coerce")
    out = out.loc[~out.index.isna()].sort_index()
    out.index.name = out.index.name or "Date"
    return out


def _pick_series(df: pd.DataFrame, candidates: Iterable[str]) -> pd.Series:
    if df is None or df.empty:
        return pd.Series(dtype="float64")

    cols = list(df.columns)
    lower_to_col = {str(c).strip().lower(): c for c in cols}

    for name in candidates:
        key = str(name).strip().lower()
        if key in lower_to_col:
            s = df[lower_to_col[key]]
            return pd.to_numeric(s, errors="coerce")

    return pd.Series(index=df.index, dtype="float64")


def _safe_div(numer: pd.Series, denom: pd.Series) -> pd.Series:
    numer, denom = numer.align(denom, join="outer")
    out = numer / denom.replace({0: np.nan})
    return out.replace([np.inf, -np.inf], np.nan)


@dataclass
class FinancialAnalyzer:
    income_statement: pd.DataFrame
    balance_sheet: pd.DataFrame
    cash_flow: pd.DataFrame
    stock_id: Optional[str] = None
    current_price: Optional[float] = None

    def __post_init__(self) -> None:
        self.income_statement = _ensure_datetime_index(self.income_statement)
        self.balance_sheet = _ensure_datetime_index(self.balance_sheet)
        self.cash_flow = _ensure_datetime_index(self.cash_flow)

    def get_current_price(self) -> Optional[float]:
        if not self.stock_id:
            return None

        symbol = self.stock_id if self.stock_id.endswith(".TW") else f"{self.stock_id}.TW"
        t = yf.Ticker(symbol)

        try:
            fast = getattr(t, "fast_info", None)
            if fast:
                for k in ("last_price", "lastPrice", "regular_market_price", "regularMarketPrice"):
                    v = fast.get(k) if hasattr(fast, "get") else None
                    if v is not None and np.isfinite(v):
                        return float(v)
        except Exception:
            pass

        try:
            hist = t.history(period="5d", interval="1d", auto_adjust=False)
            if hist is not None and not hist.empty and "Close" in hist.columns:
                close = pd.to_numeric(hist["Close"], errors="coerce").dropna()
                if not close.empty and np.isfinite(close.iloc[-1]):
                    return float(close.iloc[-1])
        except Exception:
            pass

        return None

    def summary(self) -> pd.DataFrame:
        revenue = _pick_series(
            self.income_statement,
            ["Total Revenue", "TotalRevenue", "Revenue", "Operating Revenue"],
        )
        gross_profit = _pick_series(self.income_statement, ["Gross Profit", "GrossProfit"])
        operating_income = _pick_series(
            self.income_statement,
            ["Operating Income", "OperatingIncome", "EBIT"],
        )
        net_income = _pick_series(
            self.income_statement,
            ["Net Income", "NetIncome", "Net Income Common Stockholders"],
        )

        eps = _pick_series(
            self.income_statement,
            ["Diluted EPS", "Basic EPS", "DilutedEPS", "BasicEPS", "EPS"],
        )

        total_assets = _pick_series(self.balance_sheet, ["Total Assets", "TotalAssets"])
        total_liab = _pick_series(
            self.balance_sheet,
            [
                "Total Liab",
                "TotalLiab",
                "Total Liabilities",
                "Total Liabilities Net Minority Interest",
                "TotalLiabilitiesNetMinorityInterest",
            ],
        )
        total_equity = _pick_series(
            self.balance_sheet,
            ["Total Stockholder Equity", "TotalStockholderEquity", "Total Equity Gross Minority Interest"],
        )
        current_assets = _pick_series(
            self.balance_sheet,
            ["Total Current Assets", "TotalCurrentAssets", "Current Assets"],
        )
        current_liab = _pick_series(
            self.balance_sheet,
            ["Total Current Liabilities", "TotalCurrentLiabilities", "Current Liabilities"],
        )

        free_cf = _pick_series(self.cash_flow, ["Free Cash Flow", "FreeCashFlow"])
        if free_cf.empty or free_cf.isna().all():
            cfo = _pick_series(
                self.cash_flow,
                ["Total Cash From Operating Activities", "Operating Cash Flow", "Cash Flow From Operating Activities"],
            )
            capex = _pick_series(self.cash_flow, ["Capital Expenditures", "CapitalExpenditures", "Capex"])
            free_cf = cfo - capex

        gross_margin = _safe_div(gross_profit, revenue)
        operating_margin = _safe_div(operating_income, revenue)

        avg_equity = (total_equity + total_equity.shift(1)) / 2
        roe = _safe_div(net_income, avg_equity)

        eps_growth = eps.pct_change()

        if self.current_price is None:
            self.current_price = self.get_current_price()

        pe = pd.Series(index=eps.index, dtype="float64")
        if self.current_price is not None:
            pe = self.current_price / eps.replace({0: np.nan})

        debt_ratio = _safe_div(total_liab, total_assets)
        current_ratio = _safe_div(current_assets, current_liab)

        revenue_yoy = revenue.pct_change(4)
        if revenue_yoy.isna().all():
            revenue_yoy = revenue.pct_change(1)

        idx = (
            revenue.index.union(gross_profit.index)
            .union(operating_income.index)
            .union(net_income.index)
            .union(total_assets.index)
            .union(total_liab.index)
            .union(total_equity.index)
            .union(current_assets.index)
            .union(current_liab.index)
            .union(free_cf.index)
            .union(eps.index)
        )
        idx = pd.to_datetime(idx, errors="coerce")
        idx = idx[~pd.isna(idx)]
        idx = pd.DatetimeIndex(idx).sort_values()

        out = pd.DataFrame(index=idx)
        out.index.name = "Date"

        out["Gross_Margin"] = gross_margin.reindex(idx)
        out["Operating_Margin"] = operating_margin.reindex(idx)
        out["ROE"] = roe.reindex(idx)
        out["EPS_Growth"] = eps_growth.reindex(idx)
        out["Free_Cash_Flow"] = free_cf.reindex(idx)
        out["PE"] = pe.reindex(idx)

        out["Debt_Ratio"] = debt_ratio.reindex(idx)
        out["Current_Ratio"] = current_ratio.reindex(idx)

        out["Revenue_YoY"] = revenue_yoy.reindex(idx)

        return out

