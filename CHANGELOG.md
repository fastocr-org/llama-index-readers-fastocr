# Changelog

All notable changes to this package are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[semantic versioning](https://semver.org).

## [0.1.1] - 2026-10-25

- Documentation only: the README describes the new pricing (50 free pages a month shared
  with the website, Page Packs bought on the pricing page). The SDK dependency now allows
  `fastocr-sdk` 0.3.x.

## [0.1.0] - 2026-10-24

First release. `FastOCRReader`, a LlamaIndex reader for scanned PDFs and images
(PDF, PNG, JPG, JPEG, GIF, WebP, BMP). One document per file, with `source`, `file_name`,
`fastocr_document_id`, `pages_billed` and `status` in the metadata. `output="pdf"` also saves
a searchable PDF beside the input. Needs `fastocr-sdk` 0.2.0 or later. API requests send the
User-Agent `llama-index-readers-fastocr/<version>` followed by the SDK's own.
