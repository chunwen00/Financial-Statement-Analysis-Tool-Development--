# 台股財報分析工具（Streamlit）

使用 `yfinance` 抓取台股公司三大報表，計算常用財務指標，並透過 Streamlit + Plotly 呈現趨勢圖與彙整表；另結合量化評分系統與 OpenAI API，產生帶有明確買/賣/持有建議的 AI 診斷報告。

## 功能

- 輸入台股代碼（例如 `2330`，程式會自動補上 `.TW`）
- 抓取三大報表
  - 損益表（Income Statement）
  - 資產負債表（Balance Sheet）
  - 現金流量表（Cash Flow）
- 計算指標（彙整表）
  - 獲利能力：毛利率、營業利益率、ROE、EPS 成長率、自由現金流、PE
  - 安全指標：負債比率、流動比率
  - 趨勢：近四期營收年增率（YoY）
  - 中英文欄位對照顯示
  - 本益比（PE）會自動抓取最近交易日股價計算
- Plotly 圖表
  - 近四季毛利率與營業利益率趨勢
  - ROE 走勢
- 量化評分系統（每個指標依門檻給 −2 ~ +2 分，彙總後產生 BUY / HOLD / SELL 訊號）
- AI 診斷報告（需 OpenAI API Key，使用 `gpt-4o-mini`）
  - 送入近 4 期指標趨勢與量化評分
  - 輸出財務體質總評、優點、風險、操作建議與信心分數

## 專案檔案

- `app.py`：Streamlit 網頁介面（含 AI 診斷）
- `data_loader.py`：使用 yfinance 抓取並整理三大報表
- `analyzer.py`：`FinancialAnalyzer` 計算財務指標彙整表
- `requirements.txt`：Python 套件（已固定穩定版號）
- `packages.txt`：Linux 部署時可能需要的系統依賴（字體/字形）

## 本機執行（Windows / macOS / Linux）

建立虛擬環境並安裝依賴：

```bash
python -m venv .venv
```

> 若你正在執行 `streamlit run app.py`，請先停止（關閉終端或 Ctrl+C），否則 Windows 可能會因 `streamlit.exe` 被占用而無法更新/安裝套件。

Windows PowerShell：

```bash
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

macOS / Linux：

```bash
source .venv/bin/activate
pip install -r requirements.txt
```

啟動：

```bash
streamlit run app.py
```

打開瀏覽器後：
- 在左側輸入台股代碼與（選填）OpenAI API Key
- 先按 **分析**：顯示指標彙整表與趨勢圖
- 再按 **生成 AI 診斷報告**：顯示量化評分（訊號 / 總分 / 平均分 / 得分明細）與 AI 文字報告

## 量化評分系統

每個指標依門檻給 **−2 ~ +2** 分，分數越高越偏多（買進）。

| 指標 | +2 | +1 | 0 | −1 | −2 |
|---|---|---|---|---|---|
| 毛利率 | ≥40% | ≥25% | ≥15% | ≥10% | 其餘 |
| 營業利益率 | ≥20% | ≥10% | ≥5% | ≥0% | <0% |
| ROE | ≥20% | ≥15% | ≥8% | ≥0% | <0% |
| EPS 成長率 | ≥20% | ≥5% | ≥−5% | ≥−20% | 其餘 |
| 營收年增率（YoY） | ≥15% | ≥5% | ≥−5% | ≥−15% | 其餘 |
| 流動比率 | ≥2 | ≥1.5 | ≥1 | ≥0.8 | <0.8 |
| 負債比率 | ≤30% | ≤50% | ≤60% | ≤70% | >70% |
| 本益比（PE） | ≤10 | ≤15 | ≤20 | ≤30 | >30 |
| 自由現金流 | — | 為正 +1 | — | — | 為負 −2 |

**訊號判斷（積極型）**：依各指標平均分決定

- 平均分 **≥ 0.4 → BUY（買進）**
- 平均分 **≤ −0.4 → SELL（賣出）**
- 介於兩者之間 **→ HOLD（持有）**

> 想調整積極程度：修改 `app.py` 中 `score_metrics()` 內的 `0.4` 門檻，或調整各指標的評分門檻。

## AI 診斷報告

- 模型：`gpt-4o-mini`（透過 OpenAI API）
- 輸入：近 4 期關鍵指標趨勢 + 系統量化評分
- 輸出：財務體質總評、優點、風險、操作建議（BUY / HOLD / SELL）、信心分數
- 原則上 AI 會以系統量化訊號為主；若近期趨勢明顯相反，會調整並說明理由
- API Key 由 Streamlit UI 輸入，僅保存在 session state，不會寫入檔案

## 部署提示

### 1) Python 依賴

直接使用 `requirements.txt`：

```bash
pip install -r requirements.txt
```

### 2) Linux 系統依賴（字體/中文顯示）

若你的部署平台支援 `packages.txt`（例如某些 PaaS 會自動 `apt-get install`），可使用本專案的 `packages.txt`。

若你自己管理伺服器，可用：

```bash
sudo apt-get update
sudo apt-get install -y $(cat packages.txt)
```

## 安全性提醒

- **不要把 OpenAI API Key 寫進程式碼或提交到 Git**。
- 在本專案中，Key 由 Streamlit UI 輸入並保存在 session state（不會自動寫入檔案）。

