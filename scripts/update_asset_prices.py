#!/usr/bin/env python3
"""Update asset prices in a Feishu Bitable and calculate CNY market value."""

from __future__ import annotations

import datetime as dt
import json
import os
import sys
from dataclasses import dataclass
from typing import Any

import requests

FEISHU_API = "https://open.feishu.cn/open-apis"

FIELD_NAME = "名称"
FIELD_CODE = "编码"
FIELD_CATEGORY = "类别"
FIELD_MARKET = "所属市场"
FIELD_CURRENCY = "币种"
FIELD_QUANTITY = "持仓数量"
FIELD_PRICE = "现价"
FIELD_FX = "汇率"
FIELD_MARKET_VALUE_CNY = "人民币市值"
FIELD_UPDATED_AT = "更新时间"


@dataclass
class AssetRecord:
    record_id: str
    name: str
    code: str
    category: str
    market: str
    currency: str
    quantity: float


def env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def get_tenant_access_token(app_id: str, app_secret: str) -> str:
    resp = requests.post(
        f"{FEISHU_API}/auth/v3/tenant_access_token/internal",
        json={"app_id": app_id, "app_secret": app_secret},
        timeout=20,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"Failed to get tenant token: {data}")
    return data["tenant_access_token"]


def feishu_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def normalize_select(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list) and value:
        first = value[0]
        if isinstance(first, dict):
            return str(first.get("text") or first.get("name") or first.get("value") or "")
        return str(first)
    if isinstance(value, dict):
        return str(value.get("text") or value.get("name") or value.get("value") or "")
    return str(value)


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, dict):
                parts.append(str(item.get("text") or item.get("name") or item.get("value") or ""))
            else:
                parts.append(str(item))
        return "".join(parts).strip()
    if isinstance(value, dict):
        return str(value.get("text") or value.get("name") or value.get("value") or "").strip()
    return str(value).strip()


def to_float(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = normalize_text(value).replace(",", "")
    return float(text) if text else 0.0


def list_records(token: str, app_token: str, table_id: str) -> list[AssetRecord]:
    records: list[AssetRecord] = []
    page_token = ""
    field_names = [
        FIELD_NAME,
        FIELD_CODE,
        FIELD_CATEGORY,
        FIELD_MARKET,
        FIELD_CURRENCY,
        FIELD_QUANTITY,
    ]

    while True:
        params = {"page_size": 500, "field_names": json.dumps(field_names, ensure_ascii=False)}
        if page_token:
            params["page_token"] = page_token
        resp = requests.get(
            f"{FEISHU_API}/bitable/v1/apps/{app_token}/tables/{table_id}/records",
            headers=feishu_headers(token),
            params=params,
            timeout=30,
        )
        if not resp.ok:
            raise RuntimeError(f"Failed to list records HTTP {resp.status_code}: {resp.text}")
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"Failed to list records: {data}")

        payload = data.get("data", {})
        for item in payload.get("items", []):
            fields = item.get("fields", {})
            record = AssetRecord(
                record_id=item["record_id"],
                name=normalize_text(fields.get(FIELD_NAME)),
                code=normalize_text(fields.get(FIELD_CODE)),
                category=normalize_select(fields.get(FIELD_CATEGORY)),
                market=normalize_select(fields.get(FIELD_MARKET)),
                currency=normalize_select(fields.get(FIELD_CURRENCY)) or "人民币",
                quantity=to_float(fields.get(FIELD_QUANTITY)),
            )
            if record.code and record.quantity > 0:
                records.append(record)

        if not payload.get("has_more"):
            break
        page_token = payload.get("page_token", "")
        if not page_token:
            break
    return records


def update_record(token: str, app_token: str, table_id: str, record_id: str, fields: dict[str, Any]) -> None:
    resp = requests.put(
        f"{FEISHU_API}/bitable/v1/apps/{app_token}/tables/{table_id}/records/{record_id}",
        headers=feishu_headers(token),
        json={"fields": fields},
        timeout=30,
    )
    if not resp.ok:
        raise RuntimeError(f"Failed to update record {record_id} HTTP {resp.status_code}: {resp.text}")
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"Failed to update record {record_id}: {data}")


def get_tencent_a_share_symbol(code: str) -> str:
    normalized = code.zfill(6)
    if normalized.startswith(("6", "9")):
        return f"sh{normalized}"
    if normalized.startswith(("0", "2", "3")):
        return f"sz{normalized}"
    if normalized.startswith(("4", "8")):
        return f"bj{normalized}"
    return f"sh{normalized}"


def get_tencent_a_share_price(code: str) -> float:
    symbol = get_tencent_a_share_symbol(code)
    resp = requests.get(
        f"https://qt.gtimg.cn/q={symbol}",
        headers={
            "Referer": "https://gu.qq.com/",
            "User-Agent": "Mozilla/5.0 asset-price-updater",
        },
        timeout=15,
    )
    resp.raise_for_status()
    text = resp.text.strip()
    if "~" not in text:
        raise RuntimeError(f"腾讯行情返回异常: {text[:120]}")
    payload = text.split('"', 2)[1]
    parts = payload.split("~")
    if len(parts) <= 3 or not parts[3]:
        raise RuntimeError(f"腾讯行情缺少价格字段: {text[:120]}")
    return float(parts[3])


def get_yfinance_price(symbol: str) -> float:
    import yfinance as yf

    ticker = yf.Ticker(symbol)
    errors: list[str] = []
    try:
        info = ticker.fast_info
        price = info.get("last_price") or info.get("regular_market_price")
        if price:
            return float(price)
    except Exception as exc:
        errors.append(str(exc))

    try:
        hist = ticker.history(period="5d")
        if not hist.empty:
            return float(hist["Close"].dropna().iloc[-1])
    except Exception as exc:
        errors.append(str(exc))

    detail = f": {'; '.join(errors)}" if errors else ""
    raise RuntimeError(f"yfinance 行情未找到代码 {symbol}{detail}")


def get_a_share_yfinance_symbol(code: str) -> str:
    normalized = code.zfill(6)
    if normalized.startswith(("6", "9")):
        return f"{normalized}.SS"
    if normalized.startswith(("0", "2", "3")):
        return f"{normalized}.SZ"
    if normalized.startswith(("4", "8")):
        return f"{normalized}.BJ"
    return f"{normalized}.SS"


def get_a_share_price(code: str) -> float:
    errors: list[str] = []

    try:
        import akshare as ak

        df = ak.stock_zh_a_spot_em()
        row = df[df["代码"].astype(str).str.zfill(6) == code.zfill(6)]
        if not row.empty:
            return float(row.iloc[0]["最新价"])
        errors.append(f"akshare 未找到代码 {code}")
    except Exception as exc:
        errors.append(f"akshare: {exc}")
        print(f"WARN: akshare A股行情失败，改用腾讯行情兜底: {code}: {exc}", file=sys.stderr)

    try:
        return get_tencent_a_share_price(code)
    except Exception as exc:
        errors.append(f"tencent: {exc}")
        print(f"WARN: 腾讯 A股行情失败，改用 yfinance 兜底: {code}: {exc}", file=sys.stderr)

    try:
        return get_yfinance_price(get_a_share_yfinance_symbol(code))
    except Exception as exc:
        errors.append(f"yfinance: {exc}")
        raise RuntimeError(f"A股行情获取失败 {code}: {'; '.join(errors)}") from exc


def get_hk_price(code: str) -> float:
    normalized = code.zfill(5)
    try:
        import akshare as ak

        df = ak.stock_hk_spot_em()
        code_col = "代码" if "代码" in df.columns else "symbol"
        price_col = "最新价" if "最新价" in df.columns else "lasttrade"
        row = df[df[code_col].astype(str).str.replace("HK", "", regex=False).str.zfill(5) == normalized]
        if not row.empty:
            return float(row.iloc[0][price_col])
    except Exception as exc:
        print(f"WARN: akshare 港股行情失败，改用 yfinance 兜底: {code}: {exc}", file=sys.stderr)

    return get_yfinance_price(f"{normalized}.HK")


def get_us_price(code: str) -> float:
    return get_yfinance_price(code.upper())


def get_price(record: AssetRecord) -> float:
    market = record.market.strip()
    if market == "A股":
        return get_a_share_price(record.code)
    if market == "港股":
        return get_hk_price(record.code)
    if market == "美股":
        return get_us_price(record.code)
    raise RuntimeError(f"不支持的市场: {record.market} ({record.code})")


def get_fx_rate(currency: str) -> float:
    if currency == "人民币":
        return 1.0
    code_map = {"美元": "USD", "港币": "HKD"}
    from_code = code_map.get(currency)
    if not from_code:
        raise RuntimeError(f"不支持的币种: {currency}")

    override = os.getenv(f"FX_{from_code}_CNY")
    if override:
        return float(override)

    resp = requests.get(f"https://api.frankfurter.app/latest?from={from_code}&to=CNY", timeout=15)
    resp.raise_for_status()
    data = resp.json()
    return float(data["rates"]["CNY"])


def main() -> int:
    app_id = env("FEISHU_APP_ID")
    app_secret = env("FEISHU_APP_SECRET")
    app_token = env("FEISHU_APP_TOKEN")
    table_id = env("FEISHU_TABLE_ID")

    token = get_tenant_access_token(app_id, app_secret)
    records = list_records(token, app_token, table_id)
    if not records:
        print("No records with code and quantity found; nothing to update.")
        return 0

    updated_at = dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")
    failures: list[str] = []

    for record in records:
        try:
            price = get_price(record)
            fx_rate = get_fx_rate(record.currency)
            market_value = record.quantity * price * fx_rate
            update_record(
                token,
                app_token,
                table_id,
                record.record_id,
                {
                    FIELD_PRICE: round(price, 4),
                    FIELD_FX: round(fx_rate, 4),
                    FIELD_MARKET_VALUE_CNY: round(market_value, 4),
                    FIELD_UPDATED_AT: updated_at,
                },
            )
            print(f"Updated {record.name or record.code}: price={price:.4f}, value_cny={market_value:.4f}")
        except Exception as exc:  # Keep other assets updating even if one source fails.
            message = f"{record.name or record.code}({record.code}): {exc}"
            failures.append(message)
            print(f"ERROR: {message}", file=sys.stderr)

    if failures:
        print("Some records failed to update:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
