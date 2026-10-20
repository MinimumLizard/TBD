"""CSE reports: the financials-list parsers, the cse_api:reports collector against a fake CSE (a tiny PDF made here,
converted by the real pdftotext), the history step that loads the old terminal's report texts from the archive, and
the owner's ownership confirmations (public files refuse individuals; the private file is kept). No network; every
company and person is made up."""
from __future__ import annotations

import datetime as dt
import json
import shutil

import pytest

from data_platform.collectors.cse import parse, reports
from data_platform.core import db
from data_platform.core.collector import Context
from data_platform.core.http import FetchError, Response
from data_platform.jobs import reviews
from data_platform.migration import cse_reports
from conftest import FIXTURES

SECURITIES = FIXTURES / "cse" / "2026-10-02" / "allSecurityCode.json"
NOW = dt.datetime(2026, 10, 18, 12, 0, tzinfo=dt.timezone.utc)
needs_pdftotext = pytest.mark.skipif(not shutil.which("pdftotext"), reason="pdftotext (poppler-utils) not installed")


def tiny_pdf(words: int = 300) -> bytes:
    """A one-page PDF whose text layer holds `words` words (enough to be a text, not a scanned image)."""
    lines = [" ".join(f"word{i * 10 + j}" for j in range(10)) for i in range(words // 10)]
    content = "BT /F1 9 Tf 30 800 Td 11 TL " + " ".join(f"({ln}) Tj T*" for ln in lines) + " ET"
    objs = ["<< /Type /Catalog /Pages 2 0 R >>", "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> "
            "/Contents 5 0 R >>", "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
            f"<< /Length {len(content)} >>\nstream\n{content}\nendstream"]
    out, offsets = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n{o}\nendobj\n".encode()
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return out


MS = lambda d: int(dt.datetime(*d, tzinfo=dt.timezone(dt.timedelta(hours=5, minutes=30))).timestamp() * 1000)  # noqa: E731
FINANCIALS = {
    "CIC.N0000": {"infoQuarterlyData": [
        {"id": 900, "path": "cmt/upload_report_file/old.pdf", "manualDate": MS((2026, 3, 31)), "uploadedDate": MS((2026, 5, 10)),
         "fileText": "Interim Financial Statements 31.03.2026"},
        {"id": 901, "path": "cmt/upload_report_file/q 1.pdf", "manualDate": MS((2026, 6, 30)), "uploadedDate": MS((2026, 8, 10)),
         "fileText": " Interim Financial Statements 30.06.2026 "},
        {"id": 902, "path": None, "manualDate": MS((2026, 9, 30)), "uploadedDate": MS((2026, 10, 10))}],
        "infoAnnualData": [{"id": 800, "path": "cmt/a.pdf", "manualDate": MS((2026, 3, 31)), "uploadedDate": 1}]},
    "COMB.N0000": {"infoQuarterlyData": [], "infoAnnualData": [
        {"id": 950, "path": "cmt/upload_report_file/annual.pdf", "manualDate": MS((2025, 12, 31)),
         "uploadedDate": MS((2026, 3, 1)), "fileText": "Annual Report 2025"}]},
}


def test_the_newest_quarterly_report_else_the_newest_annual_one():
    fin = parse.financials(json.dumps(FINANCIALS["CIC.N0000"]).encode(), "CIC.N0000")
    kind, item = parse.pick_report(fin)
    assert (kind, item["id"]) == ("quarterly", 901)          # 902 has no PDF; 901 is the newest with one
    e = parse.report_entry("CIC", "CIC.N0000", kind, item)
    assert e["url"] == "https://cdn.cse.lk/cmt/upload_report_file/q%201.pdf" and e["title"] == "Interim Financial Statements 30.06.2026"
    assert e["period_date"] == dt.date(2026, 6, 30) and e["uploaded_at"].tzinfo is not None
    fin = parse.financials(json.dumps(FINANCIALS["COMB.N0000"]).encode(), "COMB.N0000")
    assert parse.pick_report(fin)[0] == "annual"
    assert parse.pick_report(parse.financials(b"{}", "X.N0000")) is None
    with pytest.raises(ValueError, match="financials"):
        parse.financials(b'{"infoQuarterlyData": [{"path": "x"}]}', "X.N0000")    # no id: a changed shape fails


def test_the_financial_year_end_is_read_from_the_profile():
    assert parse.fin_year_end(b'{"reqComSumInfo": [{"finYearEnd": "2"}]}', "A.N0000")["fin_year_end"] == "2"
    assert parse.fin_year_end(b'{"reqComSumInfo": []}', "A.N0000")["fin_year_end"] is None


class FakeCse:
    def __init__(self, pdf_fails: set[str] = frozenset()):
        self.calls: list[str] = []
        self.pdf_fails = pdf_fails

    def request(self, method, url, params=None):
        params = dict(params or {})
        self.calls.append(url)
        if url.startswith("https://cdn.cse.lk/"):
            if any(f in url for f in self.pdf_fails):
                raise FetchError(f"GET {url}: HTTP 404")
            return Response(method, url, params, 200, tiny_pdf(), "application/pdf", NOW)
        ep = url.rsplit("/", 1)[-1]
        body = SECURITIES.read_bytes() if ep == "allSecurityCode" else json.dumps(FINANCIALS[params["symbol"]]).encode()
        return Response(method, url, params, 200, body, "application/json", NOW)


def make(conn, store, http):
    c = reports.CseReportsCollector(Context(conn, store, http, None, NOW))
    c.only_symbols = {"CIC.N0000", "CIC.X0000", "COMB.N0000"}
    return c


@needs_pdftotext
@pytest.mark.db
def test_reports_are_archived_converted_and_never_fetched_twice_and_failures_are_retried(conn, store):
    http = FakeCse(pdf_fails={"annual.pdf"})
    result = make(conn, store, http).collect()
    conn.commit()
    assert result.rows_added == 2 and "1 download failures" in result.message
    rows = {r["report_id"]: r for r in conn.execute("select * from cse.financial_reports_current")}
    assert rows[901]["status"] == "ok" and rows[901]["words"] == 300 and rows[901]["pages"] == 1
    assert rows[901]["pdf_sha256"] and rows[901]["text_sha256"] and rows[901]["extracted_by"].startswith("pdftotext")
    assert rows[950]["status"] == "download_failed" and rows[950]["text_sha256"] is None
    body = conn.execute("select body from cse.report_texts where sha256 = %s", (rows[901]["text_sha256"],)).fetchone()
    assert "word299" in body["body"]
    assert store.get(rows[901]["text_sha256"], "txt").decode() == body["body"]      # the text is archived too
    http2 = FakeCse()
    again = make(conn, store, http2).collect()
    conn.commit()
    assert again.rows_added == 1                                     # only the failed one, now downloaded
    assert not [u for u in http2.calls if "q%201.pdf" in u]
    assert {r["report_id"]: r["status"] for r in conn.execute("select * from cse.financial_reports_current")} == \
        {901: "ok", 950: "ok"}


def test_a_short_text_is_a_scanned_image():
    assert reports.text_status("a " * 200) == ("no_text", 200)
    assert reports.text_status("a " * 201) == ("ok", 201)


# --- the history step ---------------------------------------------------------------------------------------------

def old_repo(tmp_path):
    """The old terminal's ownership folder, in miniature (made-up company)."""
    own = tmp_path / "CSE" / "data" / "raw" / "ownership"
    (own / "text").mkdir(parents=True)
    (own / "financials").mkdir()
    (own / "annual").mkdir()
    text = (FIXTURES / "cse" / "reports" / "synthetic_interim.txt").read_bytes()
    (own / "text" / "100.txt").write_bytes(text)
    (own / "text" / "101.txt").write_bytes(b"scan")
    (own / "reports.csv").write_text(
        "id,code,symbol,kind,title,period_date,uploaded_utc,url,pages,words,status,fetched_utc\n"
        f"100,TESTCO,TESTCO.N0000,quarterly,\"Interim, 30 June 2026\",2026-06-30,2026-08-01T06:00:00Z,"
        f"https://cdn.cse.lk/100.pdf,3,{len(text.split())},ok,2026-10-07T16:42:56Z\n"
        "101,OTHER,OTHER.N0000,quarterly,Interim,2026-06-30,2026-08-02T06:00:00Z,https://cdn.cse.lk/101.pdf,2,1,"
        "no_text,2026-10-07T16:43:00Z\n")
    (own / "financials" / "TESTCO.N0000.json").write_text("{}")
    (own / "annual" / "5.json").write_text('{"passages": []}')
    (own / "annual_reports.csv").write_text("id\n5\n")
    return tmp_path / "CSE"


@pytest.mark.db
def test_the_old_report_texts_load_from_the_archive_reconcile_and_load_once(conn, store, tmp_path):
    repo = old_repo(tmp_path)
    profile = repo / "data" / "raw" / "2026-10-02" / "companyProfile" / "TESTCO.N0000.json"
    profile.parent.mkdir(parents=True)
    profile.write_text('{"reqComSumInfo": [{"finYearEnd": "1"}]}')
    db.record_fetch(conn, store, source_id="cse_api", method="POST", url="https://www.cse.lk/api/companyProfile",
                    params={"symbol": "TESTCO.N0000"}, http_status=200, body=profile.read_bytes(),
                    content_type="application/json", fetched_at=NOW, origin="migration",
                    note="MinimumLizard/CSE@abc:data/raw/2026-10-02/companyProfile/TESTCO.N0000.json")
    assert cse_reports.archive_files(conn, store, repo) == 6
    first = cse_reports.load_from_archive(conn, store)
    assert first["index_rows_added"] == 2 and first["texts_added"] == 2 and first["fiscal_year_rows_added"] == 1
    rec = cse_reports.reconcile(conn, repo)
    assert rec["ok"], rec
    assert rec["index"]["facts_matching"] == 2 and rec["texts"]["stored_text_identical"] == 2
    fy = conn.execute("select * from cse.company_fiscal_years").fetchone()
    assert (fy["session_date"], fy["fin_year_end"]) == (dt.date(2026, 10, 2), "1")
    assert cse_reports.archive_files(conn, store, repo) == 0
    again = cse_reports.load_from_archive(conn, store)
    assert again["index_rows_added"] == 0 and not again.get("texts_added") and not again.get("fiscal_year_rows_added")


@pytest.mark.db
def test_reconciliation_notices_a_text_that_differs(conn, store, tmp_path):
    repo = old_repo(tmp_path)
    cse_reports.archive_files(conn, store, repo)
    cse_reports.load_from_archive(conn, store)
    (repo / "data" / "raw" / "ownership" / "text" / "101.txt").write_bytes(b"changed")
    rec = cse_reports.reconcile(conn, repo)
    assert not rec["ok"] and rec["texts"]["facts_with_same_sha256"] == 1


# --- the owner's ownership confirmations --------------------------------------------------------------------------

def test_the_repositorys_ownership_files_are_valid_and_name_no_individual():
    public, _ = reviews.read_public()
    assert "Employees' Trust Fund Board" in public["aliases"]


def test_a_public_file_refuses_an_individual(tmp_path):
    a, p = tmp_path / "a.yaml", tmp_path / "p.yaml"
    p.write_text("parents: {}\n")
    a.write_text("aliases:\n  Mr. Q. Testperson:\n    variants: [Mr Q Testperson]\n")
    with pytest.raises(ValueError, match="private file"):
        reviews.read_public(a, p)
    a.write_text("aliases: {}\n")
    p.write_text("parents:\n  X Ltd:\n    owner: Mr. Q. Testperson\n    source: s\n    quote: q\n")
    with pytest.raises(ValueError, match="private file"):
        reviews.read_public(a, p)
    a.write_text("aliases:\n  Sample Fund:\n    colour: blue\n")
    with pytest.raises(ValueError, match="unknown fields"):
        reviews.read_public(a, p)


@pytest.mark.db
def test_the_private_file_is_stored_and_kept_when_a_run_does_not_have_it(conn, tmp_path, monkeypatch):
    a, p, private = tmp_path / "a.yaml", tmp_path / "p.yaml", tmp_path / "private.yaml"
    a.write_text("aliases: {}\n")
    p.write_text("parents: {}\n")
    private.write_text("aliases:\n  Q. Testperson:\n    variants: [Mr. Q. Testperson]\n    type: individual\n")
    monkeypatch.setenv(reviews.PRIVATE_ENV, str(private))
    assert reviews.sync_ownership(conn, a, p) == 1
    assert reviews.sync_ownership(conn, a, p) is None                  # unchanged: nothing stored
    monkeypatch.delenv(reviews.PRIVATE_ENV)
    a.write_text("aliases:\n  Sample Fund:\n    variants: [Sample Fnd]\n    type: institution\n")
    assert reviews.sync_ownership(conn, a, p) == 2                     # the public file changed ...
    last = conn.execute("select * from cse.ownership_confirmations order by version_id desc limit 1").fetchone()
    assert "Q. Testperson" in last["private"]["aliases"]                # ... and the private part was kept
    assert "Sample Fund" in last["public"]["aliases"]
