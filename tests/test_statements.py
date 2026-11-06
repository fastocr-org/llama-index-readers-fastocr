"""The bank statement reader end to end, with the FastOCR API mocked at the HTTP layer."""
import logging

import pytest
import respx
from fastocr_sdk import StatementFailedError

from llama_index.readers.fastocr import FastOCRBankStatementReader

BASE_URL = "https://api.test"
UPLOAD_URL = "https://s3.test/uploads/original?X-Amz-Signature=sig"
JSON_URL = "https://s3.test/out/statement.json?X-Amz-Signature=sig"
DATA = {
    "document": {"bank": "Example Bank"},
    "accounts": [
        {
            "account_number": "1234", "currency": "USD",
            "transactions": [
                {"date": "2026-10-02", "description": "Coffee", "amount": "5.00", "direction": "out",
                 "balance": "95.00", "page": 1, "status": "verified"},
                {"date": "2026-10-03", "description": "Refund", "amount": "25.00", "direction": "in",
                 "balance": "120.00", "page": 1, "status": "check"},
            ],
        },
        {"account_number": "9876", "currency": "USD", "transactions": [
            {"date": "2026-10-09", "description": "Fee", "amount": "1.00", "direction": "out", "balance": None, "page": 2, "status": "unchecked"},
        ]},
    ],
}


@pytest.fixture
def api():
    with respx.mock(assert_all_called=False) as router:
        yield router


def mock_statement(api, data, finished=None):
    api.post(f"{BASE_URL}/v1/bank-statements").respond(
        201, json={"id": "stmt_1", "status": "awaiting_upload", "upload_url": UPLOAD_URL, "expires_at": "x"}
    )
    api.put(UPLOAD_URL).respond(200)
    api.get(f"{BASE_URL}/v1/bank-statements/stmt_1").respond(200, json=finished or {
        "id": "stmt_1", "status": "completed", "pages_billed": 2, "needs_review": True,
        "outputs": {"json": {"available": True}},
    })
    api.get(f"{BASE_URL}/v1/bank-statements/stmt_1/output", params={"format": "json"}).respond(
        200, json={"format": "json", "url": JSON_URL, "expires_at": "x"}
    )
    api.get(JSON_URL).respond(200, json=data)


@pytest.fixture
def statement(tmp_path):
    path = tmp_path / "october.pdf"
    path.write_bytes(b"%PDF-1.4 statement")
    return path


def test_one_document_per_transaction_with_statement_facts_in_the_metadata(api, statement):
    mock_statement(api, DATA)

    docs = FastOCRBankStatementReader(api_key="fok_test", base_url=BASE_URL).load_data(statement, extra_info={"team": "ops"})

    assert [d.text for d in docs] == [
        "2026-10-02 | Coffee | out 5.00 USD | balance 95.00",
        "2026-10-03 | Refund | in 25.00 USD | balance 120.00",
        "2026-10-09 | Fee | out 1.00 USD",
    ]
    assert docs[1].metadata["fastocr_statement_id"] == "stmt_1"
    assert (docs[1].metadata["bank"], docs[1].metadata["account"], docs[1].metadata["team"]) == ("Example Bank", 1, "ops")
    assert docs[2].metadata["account"] == 2 and docs[1].metadata["needs_review"] is True
    seen = docs[1].get_content(metadata_mode="llm")
    assert "bank: Example Bank" in seen and "fastocr_statement_id" not in seen


def test_a_statement_without_transactions_warns_and_gives_nothing(api, statement, caplog):
    mock_statement(api, {"document": {}, "accounts": []})

    with caplog.at_level(logging.WARNING):
        docs = FastOCRBankStatementReader(api_key="fok_test", base_url=BASE_URL).load_data(statement)

    assert docs == [] and "no transactions" in caplog.text


def test_a_failed_statement_raises_and_bad_files_are_rejected_before_any_request(api, statement, tmp_path):
    mock_statement(api, DATA, finished={"id": "stmt_1", "status": "failed", "error": {"code": "buy_pages", "message": "Out"}})
    reader = FastOCRBankStatementReader(api_key="fok_test", base_url=BASE_URL)

    with pytest.raises(StatementFailedError) as caught:
        reader.load_data(statement)
    assert caught.value.code == "buy_pages"

    with pytest.raises(ValueError, match="PDF, PNG, JPG, JPEG and WebP"):
        reader.load_data(tmp_path / "scan.gif")
