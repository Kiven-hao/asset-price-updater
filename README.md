# Asset Price Updater

每天通过 GitHub Actions 更新飞书多维表格中的股票/基金价格，并计算人民币市值。

## 飞书表格

- Base：资产记录
- App Token：`OlNBbXSu2aSM7wsaT00cBIjgnWe`
- Table ID：`tblOiN9Gj6dirtYR`

当前脚本读取并回写以下字段：

| 字段 | 用途 |
|---|---|
| 名称 | 资产名称 |
| 编码 | 股票/基金代码，例如 `600036`、`00700`、`AAPL` |
| 类别 | 股票 / 基金 |
| 所属市场 | A股 / 港股 / 美股 |
| 币种 | 人民币 / 港币 / 美元 |
| 持仓数量 | 持有股数或基金份额 |
| 现价 | 自动更新 |
| 汇率 | 自动更新，人民币为 1 |
| 人民币市值 | 自动计算：持仓数量 * 现价 * 汇率 |
| 更新时间 | 自动更新 |

## GitHub Secrets

在 GitHub 仓库的 `Settings -> Secrets and variables -> Actions` 中配置：

```text
FEISHU_APP_ID
FEISHU_APP_SECRET
FEISHU_APP_TOKEN=OlNBbXSu2aSM7wsaT00cBIjgnWe
FEISHU_TABLE_ID=tblOiN9Gj6dirtYR
```

飞书应用需要具备多维表格读写权限，并且应用/bot 需要能访问该 Base。

## 本地运行

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

export FEISHU_APP_ID=cli_xxx
export FEISHU_APP_SECRET=xxx
export FEISHU_APP_TOKEN=OlNBbXSu2aSM7wsaT00cBIjgnWe
export FEISHU_TABLE_ID=tblOiN9Gj6dirtYR
python scripts/update_asset_prices.py
```

## 行情来源

- A股：`akshare.stock_zh_a_spot_em`
- 港股：`akshare.stock_hk_spot_em`
- 美股：`yfinance`
- 基金：优先按场内 ETF/股票行情处理；场外基金净值可后续按你的基金类型扩展。

