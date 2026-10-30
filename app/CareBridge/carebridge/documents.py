"""Turn an uploaded discharge file into text the agent can read.

Workshop Modules 1–4 start from a user sentence. A discharge companion has
to start from a hospital document. Text files are read locally. A PDF that
already contains a text layer is read locally too, including multi-page
reports, so the agent sees every page. Scanned PDFs and photos go through
Amazon Textract. Multi-page scans use the asynchronous Textract API with the
file staged in S3 when CAREBRIDGE_DOCUMENT_BUCKET is set. That document step
is the input to the Module 1 tool loop — the agent never sees the raw bytes.
"""

from __future__ import annotations

import re
import time
import uuid
from io import BytesIO
from pathlib import Path

from carebridge.config import get_settings
from carebridge.errors import DocumentError

_TEXT_SUFFIXES = {".txt", ".md", ".text", ""}
_SYNC_SUFFIXES = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".pdf"}
_MAX_SYNC_BYTES = 5_000_000
_MIN_EMBEDDED_CHARS = 80
_SAMPLE_BANNER = "=== CAREBRIDGE SAMPLE. NOT A REAL MEDICAL RECORD. ==="


def extract_upload(filename: str, data: bytes) -> str:
    if not data:
        raise DocumentError("The upload is empty.")
    if len(data) > 20 * 1024 * 1024:
        raise DocumentError("Files must be 20 MB or smaller.")

    suffix = Path(filename).suffix.lower()
    if suffix in _TEXT_SUFFIXES:
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise DocumentError("Text uploads must be UTF-8.") from exc
        return strip_sample_banner(text)

    if suffix not in _SYNC_SUFFIXES:
        raise DocumentError("Upload a PDF, a photo (PNG or JPEG), or a text file.")

    if suffix == ".pdf":
        embedded = _embedded_pdf_text(data)
        if _has_discharge_text(embedded):
            return embedded

    settings = get_settings()
    if suffix == ".pdf" and settings.document_bucket:
        return _textract_pdf_via_s3(data, filename, settings.document_bucket, settings.region)
    if len(data) > _MAX_SYNC_BYTES:
        raise DocumentError(
            "This file is too large for synchronous Textract. "
            "Set CAREBRIDGE_DOCUMENT_BUCKET so multi-page PDFs can be read from S3."
        )
    return _textract_bytes(data, settings.region)


def _embedded_pdf_text(data: bytes) -> str:
    """Read a digital PDF. A scan has no text layer and returns an empty string."""
    from pypdf import PdfReader

    try:
        reader = PdfReader(BytesIO(data))
    except Exception:
        return ""
    if reader.is_encrypted:
        try:
            if reader.decrypt("") == 0:
                return ""
        except Exception:
            return ""
    pages = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception:
            return ""
    return "\n".join(pages).strip()


def _has_discharge_text(text: str) -> bool:
    return len(re.sub(r"\s+", "", text)) >= _MIN_EMBEDDED_CHARS


def strip_sample_banner(text: str) -> str:
    lines = text.splitlines()
    if lines and lines[0].strip() == _SAMPLE_BANNER:
        return "\n".join(lines[1:]).lstrip("\n")
    return text


def _textract_bytes(data: bytes, region: str) -> str:
    import boto3

    client = boto3.client("textract", region_name=region)
    try:
        response = client.detect_document_text(Document={"Bytes": data})
    except Exception as exc:
        raise DocumentError(
            "Amazon Textract could not read this file. For a multi-page PDF, set "
            "CAREBRIDGE_DOCUMENT_BUCKET, or upload a photo of one page or a text export. "
            f"Details: {exc}"
        ) from exc
    return _lines(response)


def _textract_pdf_via_s3(data: bytes, filename: str, bucket: str, region: str) -> str:
    import boto3

    key = f"carebridge/uploads/{uuid.uuid4().hex}-{Path(filename).name}"
    s3 = boto3.client("s3", region_name=region)
    textract = boto3.client("textract", region_name=region)
    s3.put_object(Bucket=bucket, Key=key, Body=data, ContentType="application/pdf")
    job = textract.start_document_text_detection(
        DocumentLocation={"S3Object": {"Bucket": bucket, "Name": key}}
    )
    job_id = job["JobId"]
    deadline = time.monotonic() + 90
    pages: list[dict] = []
    next_token: str | None = None
    while True:
        if time.monotonic() > deadline:
            raise DocumentError("Textract did not finish within 90 seconds.")
        kwargs = {"JobId": job_id}
        if next_token:
            kwargs["NextToken"] = next_token
        result = textract.get_document_text_detection(**kwargs)
        status = result["JobStatus"]
        if status == "FAILED":
            raise DocumentError(f"Textract failed: {result.get('StatusMessage', 'unknown error')}")
        if status == "SUCCEEDED":
            pages.append(result)
            next_token = result.get("NextToken")
            if not next_token:
                break
            continue
        time.sleep(2)

    lines: list[str] = []
    for page in pages:
        lines.extend(_line_list(page))
    return "\n".join(lines).strip()


def _lines(response: dict) -> str:
    return "\n".join(_line_list(response)).strip()


def _line_list(response: dict) -> list[str]:
    return [
        block["Text"]
        for block in response.get("Blocks", [])
        if block.get("BlockType") == "LINE" and block.get("Text")
    ]
