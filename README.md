# 台股財報分析工具（Streamlit）

使用 `yfinance` 抓取台股公司三大報表，計算常用財務指標，並透過 Streamlit + Plotly 呈現趨勢圖與彙整表；可選用 OpenAI API 產生 AI 診斷報告。

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
- Plotly 圖表
  - 近四季毛利率與營業利益率趨勢
  - ROE 走勢
- AI 診斷報告（需 OpenAI API Key）

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
- 先按 **分析**
- 再按 **生成 AI 診斷報告**（需先輸入 OpenAI API Key）

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

