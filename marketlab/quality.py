"""Source provenance, not a confidence score or an independent data verifier."""
from urllib.parse import urlparse, parse_qs

PIPELINE_VERSION = "reliability-v1"


def describe_sources(evidence, as_of, created_at):
    manifest = []
    for item in evidence:
        url = item.get("url", "")
        parsed = urlparse(url)
        family = "TWSE" if parsed.hostname in ("www.twse.com.tw", "openapi.twse.com.tw") else "unknown"
        query = parse_qs(parsed.query)
        dataset = parsed.path.rstrip("/").rsplit("/", 1)[-1]
        manifest.append(dict(
            provider=family, source_family=family, dataset=dataset, url=url,
            symbol=query.get("stockNo", [None])[0],
            requested_period=query.get("date", [None])[0],
            fetched_at=item.get("fetched_at"), published_at=None,
            sha256=item.get("sha256"), raw_file=item.get("file"),
            role="primary", verification="same_upstream_only"))
    families = sorted({item["source_family"] for item in manifest})
    status = "single_source" if manifest and families == ["TWSE"] else "missing_evidence"
    return dict(
        schema_version=1, pipeline_version=PIPELINE_VERSION,
        verification_status=status, independent_verification=False,
        source_families=families, source_manifest=manifest,
        data_as_of=as_of, generated_at=created_at,
        historical_publication_versions="not_reconstructed",
        market_contract=dict(currency="TWD", price_unit="per_share", volume_unit="shares",
                             adjustment="raw", frequency="daily", timezone="Asia/Taipei"),
        limitations=["官方替代網址仍屬同一上游，尚未接入第二供應商交叉驗證。",
                     "抓取時間不是公告時間；既有歷史資料未重建當時所有修訂版本。"])


def quality_label(snapshot):
    status = snapshot.get("data_quality", {}).get("verification_status")
    return {"single_source": "單一官方來源／未完成跨來源複查",
            "missing_evidence": "來源證據不足／待複查"}.get(status, "未記錄複查狀態")
