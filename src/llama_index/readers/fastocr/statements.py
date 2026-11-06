"""Reader that loads bank statements with FastOCR, one document per transaction."""
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

from fastocr_sdk import FastOCR
from llama_index.core.readers.base import BaseReader
from llama_index.core.schema import Document

from ._version import __version__

logger = logging.getLogger(__name__)

USER_AGENT = f"llama-index-readers-fastocr/{__version__}"
SUPPORTED_SUFFIXES = (".pdf", ".png", ".jpg", ".jpeg", ".webp")

HIDDEN_FROM_MODELS = [
    "fastocr_statement_id", "account", "account_number", "page", "status", "needs_review",
]

PathLike = Union[str, Path]


def transaction_text(row: Dict[str, Any], currency: Optional[str]) -> str:
    amount = f"{row.get('direction') or ''} {row['amount']} {currency or ''}".strip() if row.get("amount") else ""
    parts = [row.get("date") or row.get("date_printed"), row.get("description"), amount]
    if row.get("balance") is not None:
        parts.append(f"balance {row['balance']}")
    return " | ".join(str(part) for part in parts if part)


class FastOCRBankStatementReader(BaseReader):
    """Load bank statements as LlamaIndex documents, one document per transaction.

    A transaction is the unit people ask about ("what did I pay this shop?"), so each
    one is its own retrievable node. Statement-level facts sit in every document's metadata.

    Args:
        api_key: A FastOCR API key. Defaults to the FASTOCR_API_KEY environment variable.
        base_url: Overrides the API address. Defaults to FASTOCR_BASE_URL, then https://api.fastocr.org.
        timeout: Seconds to wait for each statement to finish.

    Each document's text is the date, description, signed amount and balance of one
    transaction. Its metadata has source, file_name, fastocr_statement_id, bank, account
    (1 is the first), account_number, currency, date, amount, direction ("in" or "out"),
    balance, page, status ("verified", "check" or "unchecked") and needs_review (True when
    a person should check the statement). The FastOCR bookkeeping keys are left out of the
    text that embedding models and LLMs see; bank, currency, date, amount, direction and
    balance stay in it. A statement without transactions gives no documents and a logged
    warning. A failed statement raises the SDK's StatementFailedError.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        base_url: Optional[str] = None,
        timeout: float = 600.0,
    ) -> None:
        super().__init__()
        self.api_key = api_key
        self.base_url = base_url
        self.timeout = timeout

    def load_data(
        self,
        file_path: Union[PathLike, Sequence[PathLike]],
        extra_info: Optional[Dict[str, Any]] = None,
    ) -> List[Document]:
        """Read one path or a list of paths and return one Document per transaction."""
        paths = [file_path] if isinstance(file_path, (str, Path)) else list(file_path)
        files = [Path(path).expanduser() for path in paths]
        for path in files:
            if path.suffix.lower() not in SUPPORTED_SUFFIXES:
                raise ValueError(f"{path.name}: FastOCR accepts PDF, PNG, JPG, JPEG and WebP bank statements")
        documents: List[Document] = []
        with self._client() as client:
            for path in files:
                documents.extend(self._load_one(client, path, extra_info))
        return documents

    def _client(self) -> FastOCR:
        client = FastOCR(api_key=self.api_key, base_url=self.base_url)
        sdk_agent = client._http.headers.get("User-Agent", "")
        client._http.headers["User-Agent"] = f"{USER_AGENT} {sdk_agent}".strip()
        return client

    def _load_one(self, client: FastOCR, path: Path, extra_info: Optional[Dict[str, Any]]) -> List[Document]:
        job = client.extract_statement(path, timeout=self.timeout)
        data = client.bank_statements.json(job.id)
        documents: List[Document] = []
        for number, account in enumerate(data.get("accounts") or [], start=1):
            currency = account.get("currency")
            for row in account.get("transactions") or []:
                metadata: Dict[str, Any] = {
                    "source": str(path),
                    "file_name": path.name,
                    "fastocr_statement_id": job.id,
                    "bank": (data.get("document") or {}).get("bank"),
                    "account": number,
                    "account_number": account.get("account_number"),
                    "currency": currency,
                    "date": row.get("date"),
                    "amount": row.get("amount"),
                    "direction": row.get("direction"),
                    "balance": row.get("balance"),
                    "page": row.get("page"),
                    "status": row.get("status"),
                    "needs_review": job.needs_review,
                }
                metadata.update(extra_info or {})
                documents.append(
                    Document(
                        text=transaction_text(row, currency),
                        metadata=metadata,
                        excluded_embed_metadata_keys=HIDDEN_FROM_MODELS,
                        excluded_llm_metadata_keys=HIDDEN_FROM_MODELS,
                    )
                )
        if not documents:
            logger.warning("%s: no transactions were read from this statement", path.name)
        return documents
