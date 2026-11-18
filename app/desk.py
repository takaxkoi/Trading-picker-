"""Research desk (OpenBB): market movers, the Treasury yield curve and the latest SEC filings for
your watchlist, pulled through the OpenBB platform from sources that need no key (Yahoo, SEC, Federal Reserve).
Every call is wrapped so one failing source never blanks the page; failures are listed in the output.
"""
from __future__ import annotations

from datetime import datetime, timezone

from .core import SITE_DATA, load_config, log, write_json


def _records(res, limit: int = 25) -> list[dict]:
    df = res.to_df().reset_index()
    df = df.loc[:, ~df.columns.duplicated()].head(limit)
    out = []
    for row in df.to_dict("records"):
        clean = {}
        for k, v in row.items():
            if v is None or (isinstance(v, float) and v != v):
                continue
            clean[str(k)] = v.isoformat() if hasattr(v, "isoformat") else (v if isinstance(v, (int, float, bool, str)) else str(v))
        out.append(clean)
    return out


def run() -> dict:
    cfg = load_config()
    out = {"generated": datetime.now(timezone.utc).isoformat(), "errors": [], "movers": {}, "filings": [], "curve": []}
    try:
        from openbb import obb
    except Exception as e:
        out["status"] = f"OpenBB did not load: {type(e).__name__}: {str(e)[:200]}"
        write_json(SITE_DATA / "desk.json", out)
        return out

    def tryit(label, fn):
        try:
            return _records(fn())
        except Exception as e:
            out["errors"].append(f"{label}: {type(e).__name__}: {str(e)[:160]}")
            log(f"desk: {label} failed: {type(e).__name__}: {str(e)[:200]}")
            return []

    for kind in ("gainers", "losers", "active"):
        out["movers"][kind] = tryit(kind, lambda k=kind: getattr(obb.equity.discovery, k)(provider="yfinance"))[:15]
    out["curve"] = tryit("yield curve", lambda: obb.fixedincome.government.yield_curve(provider="federal_reserve"))
    keep = {"8-K", "10-Q", "10-K", "4", "SC 13D", "SC 13G", "SCHEDULE 13D", "SCHEDULE 13G", "S-1", "DEF 14A"}
    for t in [x.upper() for x in cfg.get("watchlist", [])]:
        rows = tryit(f"filings {t}", lambda t=t: obb.equity.fundamental.filings(symbol=t, provider="sec", limit=40))
        n = 0
        for r in rows:
            form = str(r.get("report_type") or r.get("form_type") or r.get("type") or "")
            if form not in keep or n >= 4:
                continue
            n += 1
            out["filings"].append({"ticker": t, "form": form, "date": str(r.get("filing_date") or r.get("report_date") or "")[:10],
                                   "url": r.get("report_url") or r.get("filing_detail_url") or r.get("filing_url") or r.get("url"),
                                   "what": str(r.get("primary_doc_description") or r.get("description") or "")[:120]})
    out["filings"].sort(key=lambda r: r["date"], reverse=True)
    out["status"] = "ok" if not out["errors"] else f"{len(out['errors'])} source calls failed"
    write_json(SITE_DATA / "desk.json", out)
    log(f"desk: {sum(len(v) for v in out['movers'].values())} movers, {len(out['filings'])} filings, {len(out['curve'])} curve points")
    try:
        from .publish import publish
        publish()
    except Exception as e:
        log(f"publish failed: {e}")
    return out


if __name__ == "__main__":
    run()
