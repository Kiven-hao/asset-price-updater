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
| 前收/上一净值 | 股票/场内基金为前收，场外基金为上一交易日净值 |
| 当日盈亏 | 实时行情资产计算：`(现价 - 前收) * 持仓数量 * 汇率` |
| 当日涨跌幅 | 实时行情资产计算：`(现价 - 前收) / 前收` |
| 昨日盈亏 | 延迟净值基金计算：`(最新净值 - 上一净值) * 持仓数量 * 汇率` |
| 净值日期 | 场外基金最新净值对应日期 |
| 行情类型 | 实时行情 / 延迟净值 |
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

- A股：优先 `akshare.stock_zh_a_spot_em`，失败后使用腾讯行情接口，再失败使用 `yfinance`
- 港股：优先 `akshare.stock_hk_spot_em`，失败后使用 `yfinance`
- 美股：`yfinance`
- 场内基金/ETF：按所属市场 `A股 / 港股 / 美股` 走实时行情，计算当日盈亏
- 场外基金：所属市场填 `场外基金`，使用 `akshare.fund_open_fund_info_em` 获取最新净值，计算昨日盈亏

