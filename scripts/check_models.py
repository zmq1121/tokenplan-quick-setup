#!/usr/bin/env python3
"""对照腾讯云官方文档核查 models.json 是否需要更新。

用法:
    python3 scripts/check_models.py          # 抓官方文档并对比
    python3 scripts/check_models.py --json   # 机器可读输出

核查逻辑:
  1. 拉取三个官方文档页(个人版 130119 / 企业专业 130659 / 企业轻享 131173),
     解析"Model Name | Model ID"表格;
  2. 与仓库 models.json 逐套餐对比:
     - 新模型:官方某行在目录中找不到任何 ID 子串匹配;
     - 已下线:目录 ID 不再出现在官方任何 ID 列;
  3. 有差异时退出码 1(可直接接入 CI 或定时任务)。

注:官方表格把同行的多个 Model ID 粘连在一起(无分隔),脚本用
"已知 ID 消去法"提取新 ID 候选,最终新增条目建议人工确认显示名。
"""
import argparse
import gzip
import html
import io
import json
import re
import sys
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MODELS_JSON = REPO / "models.json"

# 官方文档页(中国站)。套餐 key 与 models.json 对齐。
DOC_PAGES = {
    "personal-general": (
        "https://cloud.tencent.com/document/product/1823/130060",
        "tc-code-latest",  # 通用套餐表(套餐详情页,2026-09 起为权威源)
    ),
    "personal-hy": (
        "https://cloud.tencent.com/document/product/1823/130060",
        "hy3",             # Hy 套餐表(同页)
    ),
    "enterprise-pro": (
        "https://cloud.tencent.com/document/product/1823/130659",
        "Model Name",     # 专业套餐主表(页内第一处)
    ),
    "enterprise-light": (
        "https://cloud.tencent.com/document/product/1823/131173",
        "Model Name",
    ),
}

UA = "tokenplan-quick-setup-model-checker/1.0"


def fetch(url: str) -> str:
    """Fetch a doc page, transparently decoding gzip responses."""
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept-Encoding": "gzip",
    })
    with urllib.request.urlopen(req, timeout=20) as resp:
        raw = resp.read()
        if resp.headers.get("Content-Encoding", "").lower() == "gzip":
            raw = gzip.GzipFile(fileobj=io.BytesIO(raw)).read()
    return raw.decode("utf-8", errors="ignore")


MODEL_STEM = re.compile(
    r"glm|kimi|minimax|deepseek|hunyuan|hy[34]|tc-code|auto", re.I
)
# 模型 ID 列:整体为纯 ASCII [a-zA-Z0-9./_-](粘连多个 ID 也符合),
# 排除计费表("空闲时段"/"[0, 512k)"等中文或带括号的列)。
MODEL_ID_COLUMN = re.compile(r"^[a-zA-Z0-9./_-]+$")


def _clean(text: str) -> str:
    """Strip tags, entities, BOM/zero-width chars, CJK 顿号 and whitespace."""
    text = html.unescape(re.sub(r"<[^>]+>", "", text))
    return (
        text.replace("\ufeff", "").replace("\u200b", "").replace("、", "").strip()
    )


def parse_model_tables(page: str):
    """Extract (display_name, raw_ids, note) from every table that looks
    like a model table (header row 'Model Name | Model ID')."""
    out = []
    for m in re.finditer(r"<tr[^>]*>.*?</tr>", page, re.S):
        cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", m.group(0), re.S)
        cells = [_clean(c) for c in cells]
        if len(cells) < 2:
            continue
        name, raw_ids = cells[0], cells[1]
        if name in ("Model Name", "") or raw_ids in ("Model ID", ""):
            continue
        if not (MODEL_ID_COLUMN.match(raw_ids) and MODEL_STEM.search(raw_ids)):
            continue  # 计费/地域/配额等非模型表
        note = cells[3] if len(cells) > 3 else ""
        out.append((name, raw_ids, note))
    # 文档常在计费/国际站章节重复列模型,按(名称+ID)去重
    seen = set()
    deduped = []
    for row in out:
        key = (row[0], row[1])
        if key not in seen:
            seen.add(key)
            deduped.append(row)
    return deduped


def catalog_ids(entry) -> list:
    ids = []
    for line in entry.get("display", []):
        if ":" in line:
            mid = line.split(":", 1)[1].strip().split(" ")[0]
            if mid:
                ids.append(mid)
    return ids


def catalog_names(entry) -> list:
    names = []
    for line in entry.get("display", []):
        if ":" in line:
            names.append(line.split(":", 1)[0].strip())
    return names


def check_plan(plan_key: str, catalog: dict, report: dict) -> None:
    url, _anchor = DOC_PAGES[plan_key]
    page = fetch(url)
    rows = parse_model_tables(page)
    if plan_key == "personal-hy":
        rows = [r for r in rows if re.match(r"(?i)hy", r[0])]
    else:
        rows = [r for r in rows if not re.match(r"(?i)hy\d", r[0])]
    entry = catalog["plans"][plan_key]
    known_ids = catalog_ids(entry)
    known_names = catalog_names(entry)

    all_official_ids = "".join(r[1] for r in rows)
    new_rows, removed_ids = [], []

    def name_tokens(text: str) -> set:
        return {t for t in re.split(r"[\s()\[\]]+", text) if t}

    def id_boundary_match(mid: str, raw: str) -> bool:
        """Known ID must end at a real boundary so 'deepseek-v4-flash'
        does not 'match' 'deepseek/deepseek-v4-flash-vision-exp'.

        Valid boundaries: end-of-string, a '/', or a vendor prefix
        ('deepseek/...' glued right after the ID, as official tables
        concatenate multiple IDs without separators)."""
        pos = raw.find(mid)
        while pos != -1:
            end = pos + len(mid)
            if end == len(raw) or raw[end] == "/":
                return True
            # vendor-prefix glue: 'id' + 'vendor/id2' (letters then '/')
            m = re.match(r"([a-z]{2,20}/)", raw[end:])
            if m:
                return True
            pos = raw.find(mid, pos + 1)
        return False

    def row_covered(name: str, raw_ids: str) -> bool:
        # 1) 名称 token 交集(官方名与目录名共享足够多有意义 token)
        official = name_tokens(name)
        if any(
            len(official & name_tokens(n)) >= min(2, len(official))
            for n in known_names
        ):
            return True
        # 2) ID 边界匹配
        return any(id_boundary_match(mid, raw_ids) for mid in known_ids)

    for name, raw_ids, note in rows:
        if not row_covered(name, raw_ids):
            new_rows.append((name, raw_ids, note))

    for mid in known_ids:
        if mid not in all_official_ids:
            removed_ids.append(mid)

    report[plan_key] = {
        "official_rows": len(rows),
        "catalog_ids": len(known_ids),
        "new_models": [
            {"name": n, "raw_ids": i, "note": note[:80]} for n, i, note in new_rows
        ],
        "removed_ids": removed_ids,
        "url": url,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args()

    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (OSError, ValueError):
                pass

    catalog = json.loads(MODELS_JSON.read_text(encoding="utf-8"))
    report = {}
    errors = []
    for plan_key in DOC_PAGES:
        try:
            check_plan(plan_key, catalog, report)
        except Exception as exc:  # 网络/解析失败不应静默
            errors.append(f"{plan_key}: {exc}")

    if args.json:
        print(json.dumps({"errors": errors, "plans": report}, ensure_ascii=False, indent=2))
    else:
        for err in errors:
            print(f"⚠ 抓取失败 {err}")
        for plan_key, r in report.items():
            print(f"\n── {plan_key} ({r['url']}) ──")
            print(f"   官方 {r['official_rows']} 行 / 目录 {r['catalog_ids']} 个 ID")
            for m in r["new_models"]:
                print(f"   ✚ 官方新模型: {m['name']}  IDs={m['raw_ids'][:70]}")
            for mid in r["removed_ids"]:
                print(f"   ✖ 目录中的 ID 已不在官方表: {mid}")
            if not r["new_models"] and not r["removed_ids"]:
                print("   ✓ 与官方一致")

    needs_update = any(
        r["new_models"] or r["removed_ids"] for r in report.values()
    ) or bool(errors)
    if not args.json:
        if needs_update:
            print("\n结论: models.json 需要更新(见上)。")
            print("流程: 修改 models.json 与 setup.command 内置 MODEL_CATALOG →")
            print("      python3 tests/run_tests.py → 提交推送。")
        else:
            print("\n结论: models.json 与官方文档一致,无需更新。")
    return 1 if needs_update else 0


if __name__ == "__main__":
    sys.exit(main())
