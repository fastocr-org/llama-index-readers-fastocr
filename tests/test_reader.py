"""The reader end to end, with the FastOCR API mocked at the HTTP layer."""
import logging

import httpx
import pytest
import respx
from fastocr_sdk import AuthenticationError, DocumentFailedError
from llama_index.core.readers.base import BaseReader

from llama_index.readers.fastocr import FastOCRReader, __version__

BASE_URL = "https://api.test"
UPLOAD_URL = "https://s3.test/uploads/original?X-Amz-Signature=sig"
TEXT_URL = "https://s3.test/out/ocr-text.txt?X-Amz-Signature=sig"
PDF_URL = "https://s3.test/out/searchable.pdf?X-Amz-Signature=sig"


def job(doc_id, status="completed", pages=2, total=2):
    return {
        "id": doc_id,
        "status": status,
        "pages_billed": pages,
        "pages_total": total,
        "outputs": {"text": {"available": True}, "pdf": {"available": True}},
    }


@pytest.fixture
def api():
    with respx.mock(assert_all_called=False) as router:
        yield router


def mock_document(api, doc_id, finished, text):
    api.put(UPLOAD_URL).respond(200)
    api.post(f"{BASE_URL}/v1/documents/{doc_id}/start").respond(202, json={"status": "processing"})
    api.get(f"{BASE_URL}/v1/documents/{doc_id}").respond(200, json=finished)
    api.get(f"{BASE_URL}/v1/documents/{doc_id}/output", params={"format": "text"}).respond(
        200, json={"format": "text", "url": TEXT_URL + doc_id, "expires_at": "x"}
    )
    api.get(f"{BASE_URL}/v1/documents/{doc_id}/output", params={"format": "pdf"}).respond(
        200, json={"format": "pdf", "url": PDF_URL, "expires_at": "x"}
    )
    api.get(TEXT_URL + doc_id).respond(200, content=text.encode("utf-8"))


def mock_creates(api, *doc_ids):
    responses = [
        httpx.Response(201, json={"id": doc_id, "status": "awaiting_upload", "upload_url": UPLOAD_URL, "expires_at": "x"})
        for doc_id in doc_ids
    ]
    return api.post(f"{BASE_URL}/v1/documents").mock(side_effect=responses)


def read(paths, **options):
    return FastOCRReader(api_key="fok_test", base_url=BASE_URL, **options).load_data(paths)


def test_is_a_llamaindex_reader():
    assert issubclass(FastOCRReader, BaseReader)


def test_loads_an_image(api, tmp_path):
    image = tmp_path / "receipt.png"
    image.write_bytes(b"\x89PNG test")
    mock_creates(api, "doc_1")
    mock_document(api, "doc_1", job("doc_1", pages=1, total=1), "مرحبا بالعالم")

    [document] = read(image)

    assert document.text == "مرحبا بالعالم"
    assert document.metadata == {
        "source": str(image),
        "file_name": "receipt.png",
        "fastocr_document_id": "doc_1",
        "pages_billed": 1,
        "status": "completed",
    }


def test_loads_a_list_of_files_one_document_each(api, tmp_path):
    first, second = tmp_path / "a.pdf", tmp_path / "b.PDF"
    first.write_bytes(b"%PDF-1.4 a")
    second.write_bytes(b"%PDF-1.4 b")
    mock_creates(api, "doc_a", "doc_b")
    mock_document(api, "doc_a", job("doc_a"), "text of a")
    mock_document(api, "doc_b", job("doc_b"), "text of b")

    documents = read([str(first), second])

    assert [d.text for d in documents] == ["text of a", "text of b"]
    assert [d.metadata["file_name"] for d in documents] == ["a.pdf", "b.PDF"]


def test_pdf_output_saves_the_searchable_pdf_beside_the_input(api, tmp_path):
    scan = tmp_path / "scan.v2.pdf"
    scan.write_bytes(b"%PDF-1.4 scan")
    mock_creates(api, "doc_1")
    mock_document(api, "doc_1", job("doc_1"), "page text")
    api.get(PDF_URL).respond(200, content=b"%PDF searchable")

    [document] = read(scan, output="pdf")

    saved = tmp_path / "scan.v2.searchable.pdf"
    assert saved.read_bytes() == b"%PDF searchable"
    assert document.metadata["searchable_pdf_path"] == str(saved)
    assert document.text == "page text"


def test_partial_result_keeps_the_text_and_logs_a_warning(api, tmp_path, caplog):
    scan = tmp_path / "big.pdf"
    scan.write_bytes(b"%PDF-1.4 big")
    mock_creates(api, "doc_1")
    mock_document(api, "doc_1", job("doc_1", status="partial", pages=3, total=10), "first three pages")

    with caplog.at_level(logging.WARNING, logger="llama_index.readers.fastocr"):
        [document] = read(scan)

    assert document.text == "first three pages"
    assert document.metadata["status"] == "partial"
    assert "3 of 10 pages" in caplog.text


def test_failed_document_raises_the_sdk_error(api, tmp_path):
    scan = tmp_path / "bad.pdf"
    scan.write_bytes(b"%PDF-1.4 bad")
    mock_creates(api, "doc_1")
    failed = {"id": "doc_1", "status": "failed", "error": {"type": "x", "code": "buy_pages", "message": "No pages", "retryable": False}}
    mock_document(api, "doc_1", failed, "")

    with pytest.raises(DocumentFailedError) as raised:
        read(scan)

    assert raised.value.out_of_pages


def test_rejected_key_raises_authentication_error(api, tmp_path):
    scan = tmp_path / "scan.pdf"
    scan.write_bytes(b"%PDF-1.4 scan")
    api.post(f"{BASE_URL}/v1/documents").respond(401, json={"message": "Unauthorized"})

    with pytest.raises(AuthenticationError):
        read(scan)


def test_requests_name_this_package_ahead_of_the_sdk(api, tmp_path):
    scan = tmp_path / "scan.pdf"
    scan.write_bytes(b"%PDF-1.4 scan")
    create = mock_creates(api, "doc_1")
    mock_document(api, "doc_1", job("doc_1"), "text")

    read(scan)

    agent = create.calls[0].request.headers["User-Agent"]
    assert agent.startswith(f"llama-index-readers-fastocr/{__version__} fastocr-python/")


def test_unsupported_file_type_is_rejected_before_any_request(tmp_path):
    with pytest.raises(ValueError, match="notes.docx"):
        FastOCRReader(api_key="fok_test").load_data(tmp_path / "notes.docx")


def test_api_key_defaults_to_the_environment(api, tmp_path, monkeypatch):
    scan = tmp_path / "scan.pdf"
    scan.write_bytes(b"%PDF-1.4 scan")
    monkeypatch.setenv("FASTOCR_API_KEY", "fok_from_env")
    create = mock_creates(api, "doc_1")
    mock_document(api, "doc_1", job("doc_1"), "text")

    FastOCRReader(base_url=BASE_URL).load_data(scan)

    assert create.calls[0].request.headers["Authorization"] == "Bearer fok_from_env"


def test_extra_info_is_added_and_fastocr_bookkeeping_stays_out_of_model_text(api, tmp_path):
    scan = tmp_path / "scan.pdf"
    scan.write_bytes(b"%PDF-1.4 scan")
    mock_creates(api, "doc_1")
    mock_document(api, "doc_1", job("doc_1"), "text")

    [document] = FastOCRReader(api_key="fok_test", base_url=BASE_URL).load_data(scan, extra_info={"case": "A-17"})

    assert document.metadata["case"] == "A-17"
    embedded = document.get_content(metadata_mode="embed")
    assert "case: A-17" in embedded and "fastocr_document_id" not in embedded and "pages_billed" not in embedded
