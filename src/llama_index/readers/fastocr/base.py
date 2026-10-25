"""Reader that loads scanned PDFs and images with FastOCR."""
import logging
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Sequence, Union

from fastocr_sdk import FastOCR
from llama_index.core.readers.base import BaseReader
from llama_index.core.schema import Document

from ._version import __version__

logger = logging.getLogger(__name__)

USER_AGENT = f"llama-index-readers-fastocr/{__version__}"
SUPPORTED_SUFFIXES = (".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")
HIDDEN_FROM_MODELS = ["fastocr_document_id", "pages_billed", "status", "searchable_pdf_path"]

PathLike = Union[str, Path]


class FastOCRReader(BaseReader):
    """Load scanned PDFs and images as LlamaIndex documents, one document per file.

    Args:
        api_key: A FastOCR API key. Defaults to the FASTOCR_API_KEY environment variable.
        output: "text" returns the text. "pdf" also saves a searchable PDF beside each
            input file as <name>.searchable.pdf and records its path in the metadata.
        base_url: Overrides the API address. Defaults to FASTOCR_BASE_URL, then https://api.fastocr.org.
        timeout: Seconds to wait for each document to finish.

    Each document's metadata has source, file_name, fastocr_document_id, pages_billed and
    status. A "partial" status means the account ran out of pages partway: the text
    covers only the processed pages and a warning is logged. A failed document raises the
    SDK's DocumentFailedError. The FastOCR bookkeeping keys are left out of the text that
    embedding models and LLMs see.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        output: Literal["text", "pdf"] = "text",
        base_url: Optional[str] = None,
        timeout: float = 300.0,
    ) -> None:
        super().__init__()
        if output not in ("text", "pdf"):
            raise ValueError("output must be 'text' or 'pdf'")
        self.api_key = api_key
        self.output = output
        self.base_url = base_url
        self.timeout = timeout

    def load_data(
        self,
        file_path: Union[PathLike, Sequence[PathLike]],
        extra_info: Optional[Dict[str, Any]] = None,
    ) -> List[Document]:
        """Read one path or a list of paths and return one Document per file."""
        paths = [file_path] if isinstance(file_path, (str, Path)) else list(file_path)
        files = [Path(path).expanduser() for path in paths]
        for path in files:
            if path.suffix.lower() not in SUPPORTED_SUFFIXES:
                raise ValueError(f"{path.name}: FastOCR accepts PDF, PNG, JPG, JPEG, GIF, WebP and BMP files")
        with self._client() as client:
            return [self._load_one(client, path, extra_info) for path in files]

    def _client(self) -> FastOCR:
        client = FastOCR(api_key=self.api_key, base_url=self.base_url)
        sdk_agent = client._http.headers.get("User-Agent", "")
        client._http.headers["User-Agent"] = f"{USER_AGENT} {sdk_agent}".strip()
        return client

    def _load_one(self, client: FastOCR, path: Path, extra_info: Optional[Dict[str, Any]]) -> Document:
        job = client.documents.process(path, timeout=self.timeout)
        if job.is_partial:
            logger.warning(
                "%s: only %s of %s pages were processed because the account ran out of pages",
                path.name,
                job.pages_billed,
                job.pages_total,
            )
        metadata: Dict[str, Any] = {
            "source": str(path),
            "file_name": path.name,
            "fastocr_document_id": job.id,
            "pages_billed": job.pages_billed,
            "status": job.status,
        }
        text = client.documents.get_text(job.id)
        if self.output == "pdf":
            destination = path.with_name(f"{path.stem}.searchable.pdf")
            client.documents.download_searchable_pdf(job.id, destination)
            metadata["searchable_pdf_path"] = str(destination)
        metadata.update(extra_info or {})
        return Document(
            text=text,
            metadata=metadata,
            excluded_embed_metadata_keys=HIDDEN_FROM_MODELS,
            excluded_llm_metadata_keys=HIDDEN_FROM_MODELS,
        )
