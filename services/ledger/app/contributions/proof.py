"""Suggest payment details from an uploaded proof; never post to the ledger."""

from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
import re
import subprocess
from tempfile import TemporaryDirectory
from pathlib import Path

from pypdf import PdfReader


MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_PAGES = 3


class ProofError(ValueError):
    pass


@dataclass(frozen=True)
class ProofSuggestion:
    payment_date: str | None
    amount_cents: int | None
    reference: str | None
    warnings: list[str]


def _ocr(path: Path) -> str:
    try:
        result = subprocess.run(
            ["tesseract", str(path), "stdout", "-l", "eng"],
            capture_output=True,
            text=True,
            timeout=20,
            check=True,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ProofError("Could not read image text") from exc
    return result.stdout


def extract_proof_text(data: bytes) -> str:
    if not data or len(data) > MAX_FILE_BYTES:
        raise ProofError("Proof must be between 1 byte and 5 MB")

    if data.startswith(b"%PDF-"):
        try:
            reader = PdfReader(BytesIO(data), strict=False)
            if reader.is_encrypted or len(reader.pages) > MAX_PAGES:
                raise ProofError("PDF must be unencrypted and at most 3 pages")
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
        except ProofError:
            raise
        except Exception as exc:
            raise ProofError("Could not read PDF") from exc
        if text.strip():
            return text
        with TemporaryDirectory() as directory:
            pdf = Path(directory) / "proof.pdf"
            pdf.write_bytes(data)
            try:
                subprocess.run(
                    ["pdftoppm", "-f", "1", "-l", str(MAX_PAGES), "-r", "150", "-png", str(pdf), str(Path(directory) / "page")],
                    capture_output=True,
                    timeout=30,
                    check=True,
                )
            except (OSError, subprocess.SubprocessError) as exc:
                raise ProofError("Could not read scanned PDF") from exc
            return "\n".join(_ocr(page) for page in sorted(Path(directory).glob("page-*.png")))

    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        suffix = ".png"
    elif data.startswith(b"\xff\xd8\xff"):
        suffix = ".jpg"
    else:
        raise ProofError("Upload a PDF, PNG, or JPEG proof")
    with TemporaryDirectory() as directory:
        image = Path(directory) / f"proof{suffix}"
        image.write_bytes(data)
        return _ocr(image)


def suggest_proof_fields(text: str) -> ProofSuggestion:
    # Labels keep account numbers and unrelated dates out of the suggestion.
    date_match = re.search(
        r"(?im)^\s*(?:payment|transaction|transfer)\s*date\s*[:\-]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{4}|\d{4}-\d{2}-\d{2})",
        text,
    )
    amount_match = re.search(
        r"(?im)^\s*(?:payment\s+)?amount\s*[:\-]?\s*R\s*([\d ,]+\.\d{2})\b",
        text,
    )
    reference_match = re.search(
        r"(?im)^\s*(?:payment\s+)?reference\s*[:\-]?\s*([^\r\n]{1,200})",
        text,
    )

    payment_date = None
    if date_match:
        value = date_match.group(1)
        for pattern in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"):
            try:
                payment_date = datetime.strptime(value, pattern).date().isoformat()
                break
            except ValueError:
                pass

    amount_cents = None
    if amount_match:
        value = amount_match.group(1).replace(" ", "").replace(",", "")
        whole, cents = value.split(".")
        amount_cents = int(whole) * 100 + int(cents)

    reference = reference_match.group(1).strip(" :-") if reference_match else None
    warnings = ["Check these details against the proof and bank statement before confirming."]
    if not payment_date or amount_cents is None or not reference:
        warnings.append("Some fields could not be read; enter them manually.")
    return ProofSuggestion(payment_date, amount_cents, reference or None, warnings)


def inspect_proof(data: bytes) -> ProofSuggestion:
    return suggest_proof_fields(extract_proof_text(data))
