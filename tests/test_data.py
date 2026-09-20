import io
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from marketlab.data import TwseClient


class DownloadTests(unittest.TestCase):
    def test_standard_request_avoids_header_dependent_redirect_loop(self):
        url="https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY?response=json&date=20241001&stockNo=0056"
        payload={"stat":"OK","data":[["113/10/01","100"]]}
        def request(req,timeout):
            if req.has_header("Accept") or req.has_header("User-agent"):
                raise HTTPError(url,308,"self redirect with custom headers",{"Location":url},None)
            return io.BytesIO(json.dumps(payload).encode())
        with tempfile.TemporaryDirectory() as root,patch("marketlab.data.urlopen",side_effect=request),patch("marketlab.data.time.sleep"):
            client=TwseClient(root)
            self.assertEqual(client.fetch("header-regression",url),payload)
            self.assertEqual(client.evidence[-1]["url"],url)

    def test_official_fallback_retains_data_and_source_evidence(self):
        primary="https://www.twse.com.tw/exchangeReport/STOCK_DAY?response=json&date=20250501&stockNo=2454"
        alternate="https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY?response=json&date=20250501&stockNo=2454"
        payload={"stat":"OK","data":[["114/05/02","100"]]}
        def request(req,timeout):
            if req.full_url==primary: raise HTTPError(primary,308,"redirect loop",{},None)
            if req.full_url==alternate: return io.BytesIO(json.dumps(payload).encode())
            raise AssertionError("unapproved URL")
        with tempfile.TemporaryDirectory() as root,patch("marketlab.data.urlopen",side_effect=request),patch("marketlab.data.time.sleep"):
            client=TwseClient(root)
            actual=client.fetch("sample",primary)
            self.assertEqual(actual,payload)
            self.assertEqual(client.evidence[-1]["url"],alternate)
            saved=json.loads((Path(root)/"raw"/client.evidence[-1]["file"]).read_text())
            self.assertEqual(saved,payload)


class MonthlyCacheTests(unittest.TestCase):
    fields=["日期","成交股數","成交金額","開盤價","最高價","最低價","收盤價","漲跌價差","成交筆數"]

    def payload(self,kind,days):
        if kind=="stock":
            return dict(stat="OK",fields=self.fields,data=[
                [day,"1000","100000","100","101","99","100","0","10"] for day in days])
        return dict(stat="OK",fields=["日期","成交股數","成交金額","成交筆數","發行量加權股價指數","漲跌點數"],data=[
            [day,"1000","100000","10","20000","0"] for day in days])

    def download(self,payload):
        def request(req,timeout):
            if "/holidaySchedule/" in req.full_url:
                return io.BytesIO(b'{"stat":"OK","data":[]}')
            if "/exchangeReport/STOCK_DAY?" in req.full_url or "/exchangeReport/FMTQIK?" in req.full_url:
                return io.BytesIO(json.dumps(payload).encode())
            raise AssertionError("unapproved URL: "+req.full_url)
        return request

    def read(self,client,kind,month):
        return client.stock("2330",[month]) if kind=="stock" else client.calendar([month])

    def dates(self,result,kind):
        return [row["date"] for row in result["rows"]] if kind=="stock" else result["actual"]

    def at(self,value):
        # Mock only acquisition time and the external transport; real cache IO remains active.
        instant=datetime.fromisoformat(value)
        return patch.multiple("marketlab.data",now=lambda:instant),patch("marketlab.data.time.time",return_value=instant.timestamp())

    def test_in_progress_month_refreshes_after_an_entire_skipped_month(self):
        for kind in ("stock","market"):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as root,patch("marketlab.data.time.sleep"):
                clock,epoch=self.at("2026-09-01T20:00:00+08:00")
                with clock,epoch,patch("marketlab.data.urlopen",side_effect=self.download(self.payload(kind,["115/09/01"]))):
                    first=TwseClient(root)
                    self.read(first,kind,"20260901")
                original=first.evidence[0]
                original_path=Path(root)/"raw"/original["file"]
                original_text=original_path.read_text(encoding="utf-8")
                clock,epoch=self.at("2026-11-01T20:00:00+08:00")
                with clock,epoch,patch("marketlab.data.urlopen",side_effect=self.download(self.payload(kind,["115/09/01","115/09/30"]))):
                    refreshed=TwseClient(root)
                    result=self.read(refreshed,kind,"20260901")
                self.assertEqual(self.dates(result,kind),["2026-09-01","2026-09-30"])
                latest=refreshed.evidence[0]
                self.assertNotEqual(original["sha256"],latest["sha256"])
                self.assertEqual(original_path.read_text(encoding="utf-8"),original_text)
                self.assertEqual(latest["fetched_at"],"2026-11-01T20:00:00+08:00")
                self.assertEqual(latest["url"],original["url"])

    def test_closed_month_reuses_finalized_acquisition_and_its_provenance(self):
        for kind in ("stock","market"):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as root,patch("marketlab.data.time.sleep"):
                clock,epoch=self.at("2026-10-01T00:00:00+08:00")
                with clock,epoch,patch("marketlab.data.urlopen",side_effect=self.download(self.payload(kind,["115/09/01","115/09/30"]))):
                    first=TwseClient(root)
                    self.read(first,kind,"20260901")
                clock,epoch=self.at("2026-11-01T20:00:00+08:00")
                def request(req,timeout):
                    if "/holidaySchedule/" in req.full_url: return io.BytesIO(b'{"stat":"OK","data":[]}')
                    raise AssertionError("finalized month unexpectedly downloaded")
                with clock,epoch,patch("marketlab.data.urlopen",side_effect=request):
                    cached=TwseClient(root)
                    result=self.read(cached,kind,"20260901")
                self.assertEqual(self.dates(result,kind),["2026-09-01","2026-09-30"])
                self.assertEqual(cached.evidence[0],first.evidence[0])

    def test_acquisition_on_last_day_is_not_finalized(self):
        with tempfile.TemporaryDirectory() as root,patch("marketlab.data.time.sleep"):
            clock,epoch=self.at("2026-09-30T23:59:59+08:00")
            with clock,epoch,patch("marketlab.data.urlopen",side_effect=self.download(self.payload("stock",["115/09/01"]))):
                self.read(TwseClient(root),"stock","20260901")
            clock,epoch=self.at("2026-11-01T20:00:00+08:00")
            with clock,epoch,patch("marketlab.data.urlopen",side_effect=self.download(self.payload("stock",["115/09/01","115/09/30"]))):
                result=self.read(TwseClient(root),"stock","20260901")
            self.assertEqual(self.dates(result,"stock"),["2026-09-01","2026-09-30"])

    def test_corrupt_month_cache_is_refetched(self):
        cases=("invalid_json","not_object","missing_hash","bad_acquisition","missing_acquisition","bad_timestamp",
               "future_timestamp","wrong_url","unsafe_path","changed_raw","invalid_raw_json","invalid_raw_shape")
        for kind in ("stock","market"):
            for corruption in cases:
                with self.subTest(kind=kind,corruption=corruption),tempfile.TemporaryDirectory() as root,patch("marketlab.data.time.sleep"):
                    clock,epoch=self.at("2026-10-01T20:00:00+08:00")
                    with clock,epoch,patch("marketlab.data.urlopen",side_effect=self.download(self.payload(kind,["115/09/01"]))):
                        seeded=TwseClient(root)
                        self.read(seeded,kind,"20260901")
                    key="stock-2330-20260901" if kind=="stock" else "market-20260901"
                    pointer=Path(root)/"raw"/(key+".latest.json")
                    metadata=json.loads(pointer.read_text(encoding="utf-8"))
                    if corruption=="invalid_json": pointer.write_text("{",encoding="utf-8")
                    elif corruption=="not_object": pointer.write_text("[]",encoding="utf-8")
                    else:
                        if corruption=="missing_hash": metadata.pop("sha256")
                        elif corruption=="bad_acquisition": metadata["fetched_at"]="bad date"
                        elif corruption=="missing_acquisition": metadata.pop("fetched_at")
                        elif corruption=="bad_timestamp": metadata["timestamp"]="yesterday"
                        elif corruption=="future_timestamp": metadata["timestamp"]=datetime(2027,1,1,tzinfo=timezone.utc).timestamp()
                        elif corruption=="wrong_url": metadata["url"]="https://example.invalid/unrelated"
                        elif corruption=="unsafe_path": metadata["file"]="../outside.json"
                        elif corruption=="changed_raw": (Path(root)/"raw"/metadata["file"]).write_text("{}",encoding="utf-8")
                        elif corruption in ("invalid_raw_json","invalid_raw_shape"):
                            text="{" if corruption=="invalid_raw_json" else "null"
                            metadata["sha256"]=hashlib.sha256(text.encode()).hexdigest()
                            metadata["file"]=f"{key}-{metadata['sha256'][:16]}.json"
                            (Path(root)/"raw"/metadata["file"]).write_text(text,encoding="utf-8")
                        pointer.write_text(json.dumps(metadata),encoding="utf-8")
                    clock,epoch=self.at("2026-11-01T20:00:00+08:00")
                    with clock,epoch,patch("marketlab.data.urlopen",side_effect=self.download(self.payload(kind,["115/09/01","115/09/30"]))):
                        repaired=TwseClient(root)
                        result=self.read(repaired,kind,"20260901")
                    self.assertEqual(self.dates(result,kind),["2026-09-01","2026-09-30"])
                    self.assertEqual(repaired.evidence[0]["fetched_at"],"2026-11-01T20:00:00+08:00")

    def test_redownload_repairs_corrupt_raw_file_when_official_content_is_unchanged(self):
        payload=self.payload("stock",["115/09/01","115/09/30"])
        with tempfile.TemporaryDirectory() as root,patch("marketlab.data.time.sleep"):
            clock,epoch=self.at("2026-10-01T20:00:00+08:00")
            with clock,epoch,patch("marketlab.data.urlopen",side_effect=self.download(payload)):
                first=TwseClient(root)
                self.read(first,"stock","20260901")
            raw=Path(root)/"raw"/first.evidence[0]["file"]
            raw.write_text("{}",encoding="utf-8")
            clock,epoch=self.at("2026-11-01T20:00:00+08:00")
            with clock,epoch,patch("marketlab.data.urlopen",side_effect=self.download(payload)):
                repaired=TwseClient(root)
                result=self.read(repaired,"stock","20260901")
            self.assertEqual(self.dates(result,"stock"),["2026-09-01","2026-09-30"])
            self.assertEqual(hashlib.sha256(raw.read_bytes()).hexdigest(),repaired.evidence[0]["sha256"])
            self.assertEqual(json.loads(raw.read_text(encoding="utf-8")),payload)


if __name__=="__main__": unittest.main()
