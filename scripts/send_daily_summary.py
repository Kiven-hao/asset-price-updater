#!/usr/bin/env python3
"""Send a daily asset summary from Feishu Bitable through PushPlus."""

from __future__ import annotations

import datetime as dt
import json
import os
from typing import Any

import requests

from update_asset_prices import (
    FEISHU_API,
    FIELD_CODE,
    FIELD_DAILY_PNL,
    FIELD_MARKET_VALUE_CNY,
    FIELD_NAME,
    FIELD_PRICE,
    FIELD_QUOTE_TYPE,
    FIELD_UPDATED_AT,
    FIELD_YESTERDAY_PNL,
    env,
    feishu_headers,
    get_tenant_access_token,
    normalize_select,
    normalize_text,
    to_float,
)

PUSHPLUS_SEND_URL = "https://www.pushplus.plus/send"


def list_summary_rows(token: str, app_token: str, table_id: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    page_token = ""
    field_names = [
        FIELD_NAME,
        FIELD_CODE,
        FIELD_PRICE,
        FIELD_MARKET_VALUE_CNY,
        FIELD_DAILY_PNL,
        FIELD_YESTERDAY_PNL,
        FIELD_QUOTE_TYPE,
        FIELD_UPDATED_AT,
    ]

    while True:
        params: dict[str, Any] = {
            "page_size": 500,
            "field_names": json.dumps(field_names, ensure_ascii=False),
        }
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
            market_value = to_float(fields.get(FIELD_MARKET_VALUE_CNY))
            daily_pnl = to_float(fields.get(FIELD_DAILY_PNL))
            yesterday_pnl = to_float(fields.get(FIELD_YESTERDAY_PNL))
            if market_value == 0 and daily_pnl == 0 and yesterday_pnl == 0:
                continue
            rows.append(
                {
                    "name": normalize_text(fields.get(FIELD_NAME)) or normalize_text(fields.get(FIELD_CODE)) or item["record_id"],
                    "code": normalize_text(fields.get(FIELD_CODE)),
                    "price": to_float(fields.get(FIELD_PRICE)),
                    "market_value": market_value,
                    "daily_pnl": daily_pnl,
                    "yesterday_pnl": yesterday_pnl,
                    "quote_type": normalize_select(fields.get(FIELD_QUOTE_TYPE)),
                }
            )

        if not payload.get("has_more"):
            break
        page_token = payload.get("page_token", "")
        if not page_token:
            break
    return rows


def money(value: float) -> str:
    sign = "+" if value > 0 else ""
    return f"{sign}{value:,.2f}"


def build_markdown(rows: list[dict[str, Any]]) -> tuple[str, str]:
    today = dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).strftime("%Y-%m-%d")
    total_value = sum(row["market_value"] for row in rows)
    realtime_pnl = sum(row["daily_pnl"] for row in rows)
    delayed_pnl = sum(row["yesterday_pnl"] for row in rows)
    yesterday_pnl_total = realtime_pnl + delayed_pnl

    title = f"资产日报 {today}"
    lines = [
        f"# {title}",
        "",
        f"- 当前资产总额：**{total_value:,.2f} 元**",
        f"- 昨日盈亏合计：**{money(yesterday_pnl_total)} 元**",
        f"- 实时行情部分：{money(realtime_pnl)} 元",
        f"- 延迟净值部分：{money(delayed_pnl)} 元",
        "",
        "| 资产 | 行情类型 | 现价/净值 | 当前市值 | 昨日盈亏 |",
        "|---|---:|---:|---:|---:|",
    ]

    sorted_rows = sorted(rows, key=lambda row: abs(row["daily_pnl"] + row["yesterday_pnl"]), reverse=True)
    for row in sorted_rows[:20]:
        pnl = row["daily_pnl"] + row["yesterday_pnl"]
        lines.append(
            f"| {row['name']} | {row['quote_type'] or '-'} | {row['price']:,.4f} | "
            f"{row['market_value']:,.2f} | {money(pnl)} |"
        )

    if len(rows) > 20:
        lines.append(f"\n> 仅展示盈亏波动最大的 20 条，共 {len(rows)} 条资产。")
    return title, "\n".join(lines)


def send_pushplus(token: str, title: str, content: str) -> None:
    payload: dict[str, Any] = {
        "token": token,
        "title": title,
        "content": content,
        "template": "markdown",
    }
    topic = os.getenv("PUSHPLUS_TOPIC")
    if topic:
        payload["topic"] = topic

    resp = requests.post(PUSHPLUS_SEND_URL, json=payload, timeout=30)
    if not resp.ok:
        raise RuntimeError(f"PushPlus HTTP {resp.status_code}: {resp.text}")
    data = resp.json()
    if data.get("code") != 200:
        raise RuntimeError(f"PushPlus send failed: {data}")


def main() -> int:
    app_id = env("FEISHU_APP_ID")
    app_secret = env("FEISHU_APP_SECRET")
    app_token = env("FEISHU_APP_TOKEN")
    table_id = env("FEISHU_TABLE_ID")
    pushplus_token = env("PUSHPLUS_TOKEN")

    feishu_token = get_tenant_access_token(app_id, app_secret)
    rows = list_summary_rows(feishu_token, app_token, table_id)
    title, content = build_markdown(rows)
    send_pushplus(pushplus_token, title, content)
    print(f"Sent PushPlus summary: rows={len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
