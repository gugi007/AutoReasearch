import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from services.pdf_downloader import PDFDownloader


class PDFDownloaderTests(unittest.TestCase):
    def setUp(self):
        self.downloader = PDFDownloader(pdf_dir=ROOT / ".tmp_test_papers")

    def test_prefers_explicit_pdf_url(self):
        url = self.downloader._resolve_pdf_url(
            "https://example.com/landing",
            pdf_url="https://example.com/paper.pdf",
        )

        self.assertEqual(url, "https://example.com/paper.pdf")

    def test_resolves_arxiv_abs_to_pdf(self):
        url = self.downloader._resolve_pdf_url("https://arxiv.org/abs/2401.12345")

        self.assertEqual(url, "https://arxiv.org/pdf/2401.12345.pdf")

    def test_skips_doi_without_unpaywall_email(self):
        with patch.dict("os.environ", {}, clear=True):
            url = self.downloader._resolve_pdf_url("https://doi.org/10.1000/test")

        self.assertIsNone(url)

    def test_skips_regular_landing_page(self):
        url = self.downloader._resolve_pdf_url("https://publisher.example/paper")

        self.assertIsNone(url)


if __name__ == "__main__":
    unittest.main()
