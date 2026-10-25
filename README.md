<div align="center">

<a href="https://fastocr.org">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/fastocr-org/llama-index-readers-fastocr/main/docs/images/logo-dark.png">
    <img src="https://raw.githubusercontent.com/fastocr-org/llama-index-readers-fastocr/main/docs/images/logo-light.png" alt="FastOCR" width="200">
  </picture>
</a>

<h3>A LlamaIndex reader that reads scanned PDFs and images with FastOCR and returns their text.</h3>

<p>
<a href="https://github.com/fastocr-org/llama-index-readers-fastocr/actions/workflows/ci.yml"><img src="https://github.com/fastocr-org/llama-index-readers-fastocr/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
<a href="https://pypi.org/project/llama-index-readers-fastocr/"><img src="https://img.shields.io/pypi/v/llama-index-readers-fastocr.svg?label=pypi" alt="PyPI"></a>
<a href="https://pypi.org/project/llama-index-readers-fastocr/"><img src="https://img.shields.io/pypi/pyversions/llama-index-readers-fastocr.svg" alt="Python"></a>
<a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue.svg" alt="License: MIT"></a>
</p>

<p>
<a href="https://fastocr.org">Website</a> ·
<a href="https://fastocr.org/docs">Docs</a> ·
<a href="https://fastocr.org/developers/keys">Get an API key</a>
</p>

<img src="https://raw.githubusercontent.com/fastocr-org/llama-index-readers-fastocr/main/docs/images/readme-hero.gif" alt="FastOCR reads a scanned page in English, Arabic and Hindi and returns its text" width="800">

</div>

## Quickstart

```bash
pip install llama-index-readers-fastocr
export FASTOCR_API_KEY="your_api_key"
```

```python
from llama_index.readers.fastocr import FastOCRReader

documents = FastOCRReader().load_data("scanned_contract.pdf")
print(documents[0].text)
```

Python 3.10 or newer. The distribution is `llama-index-readers-fastocr` and the import is `llama_index.readers.fastocr`.

## What you get back

`FastOCRReader.load_data` returns one `Document` per file.

| You get | Where |
|---|---|
| The text of the whole file | `text` |
| The file's path and name | `metadata["source"]`, `metadata["file_name"]` |
| The FastOCR document id | `metadata["fastocr_document_id"]` |
| Pages billed | `metadata["pages_billed"]` |
| `completed` or `partial` | `metadata["status"]` |
| A searchable PDF, with `output="pdf"` | saved as `<name>.searchable.pdf` beside the input; its path is in `metadata["searchable_pdf_path"]` |

The FastOCR keys (`fastocr_document_id`, `pages_billed`, `status`, `searchable_pdf_path`) are left out of the text that embedding models and LLMs see. Pass `extra_info={...}` to `load_data` to add your own metadata.

If the account runs out of pages partway through a file, you still get the text of the pages that were processed, with `status` set to `partial` and a warning in the log. A document that fails raises the error from [`fastocr-sdk`](https://pypi.org/project/fastocr-sdk/) with its message and code.

## Languages and files

- 100+ languages, detected automatically. No language setting is needed.
- PDF files up to 1 GiB, and PNG, JPG, JPEG, GIF, WebP and BMP images up to 20 MiB. An image counts as one page.

## Get an API key and pages

Any signed-in FastOCR account can create an API key and start right away.

1. Sign in and create an API key in the [developer console](https://fastocr.org/developers/keys). You accept the [API terms](https://fastocr.org/api-terms) with your first key.
2. Set the key as `FASTOCR_API_KEY`, or pass `api_key=` to the reader.
3. When you need more than the free pages, buy a Page Pack on the [pricing page](https://fastocr.org/pricing?from=api#packs). Packs work on the website and in the API.

Every account gets 50 free pages a month, shared with PDFs on the website. An image sent to the API is one page.

## Examples

### RAG over scanned PDFs

```python
from llama_index.core import VectorStoreIndex
from llama_index.readers.fastocr import FastOCRReader

documents = FastOCRReader().load_data("scanned_contract.pdf")
index = VectorStoreIndex.from_documents(documents)
print(index.as_query_engine().query("When can the contract be terminated?"))
```

This example uses LlamaIndex's default OpenAI models, so it needs `OPENAI_API_KEY`. Set another embedding model and LLM in `Settings` to use a different provider.

### A folder of scans

```python
from pathlib import Path

from llama_index.readers.fastocr import FastOCRReader

scans = sorted(p for p in Path("scans").iterdir() if p.suffix.lower() in {".pdf", ".png", ".jpg", ".jpeg"})
for document in FastOCRReader().load_data(scans):
    print(document.metadata["file_name"], document.metadata["pages_billed"])
```

The reader runs one file at a time and returns when all files are done.

### Use it with SimpleDirectoryReader

```python
from llama_index.core import SimpleDirectoryReader
from llama_index.readers.fastocr import FastOCRReader

documents = SimpleDirectoryReader(
    "scans",
    file_extractor={".pdf": FastOCRReader(), ".png": FastOCRReader(), ".jpg": FastOCRReader()},
).load_data()
```

### Searchable PDFs for an archive

```python
from llama_index.readers.fastocr import FastOCRReader

documents = FastOCRReader(output="pdf").load_data(["invoice-001.pdf", "invoice-002.pdf"])
for document in documents:
    print(document.metadata["searchable_pdf_path"])
```

Each searchable PDF is saved beside its input, as `invoice-001.searchable.pdf`. An existing file with that name is replaced. Index the text and keep the PDF.

## Options

| Argument | Default | Meaning |
|---|---|---|
| `api_key` | `FASTOCR_API_KEY` | Your FastOCR API key |
| `output` | `"text"` | `"pdf"` also saves a searchable PDF beside each input |
| `base_url` | `FASTOCR_BASE_URL`, then `https://api.fastocr.org` | API address |
| `timeout` | `300.0` | Seconds to wait for each document |

`load_data(file_path, extra_info=None)` takes one path or a list of paths.

## Support and license

Questions: support@fastocr.org. Bugs and requests: [GitHub issues](https://github.com/fastocr-org/llama-index-readers-fastocr/issues). MIT license; see [LICENSE](LICENSE).
