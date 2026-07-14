import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from services import academic_search


def payload(source, title, citations=0, **extra):
    item = {
        "title": title,
        "url": extra.pop("url", f"https://example.com/{source}"),
        "content": f"来源: {source}",
        "raw_content": extra.pop("raw_content", ""),
        "authors": extra.pop("authors", ""),
        "year": extra.pop("year", 2024),
        "venue": extra.pop("venue", ""),
        "citations": citations,
        "source": source,
    }
    item.update(extra)
    return {"results": [item], "notices": []}


class AcademicSearchTests(unittest.TestCase):
    def test_aggregate_merges_duplicate_titles(self):
        with (
            patch.object(
                academic_search,
                "_search_openalex",
                return_value=payload("openalex", "Efficient Attention Mechanisms", 10, doi="10/a"),
            ),
            patch.object(
                academic_search,
                "_search_semantic_scholar",
                return_value=payload(
                    "semantic_scholar",
                    "Efficient Attention Mechanisms.",
                    22,
                    raw_content="abstract",
                ),
            ),
            patch.object(
                academic_search,
                "_search_arxiv",
                return_value={"results": [], "notices": []},
            ),
            patch.object(
                academic_search,
                "_search_crossref",
                return_value={"results": [], "notices": []},
            ),
        ):
            result = academic_search.search_academic("efficient attention", max_results=5)

        self.assertEqual(len(result["results"]), 1)
        paper = result["results"][0]
        self.assertEqual(paper["citations"], 22)
        self.assertEqual(paper["doi"], "10/a")
        self.assertEqual(set(paper["source"]), {"openalex", "semantic_scholar"})

    def test_google_scholar_is_disabled_by_default(self):
        with (
            patch.object(academic_search, "_search_openalex", return_value={"results": [], "notices": []}),
            patch.object(academic_search, "_search_semantic_scholar", return_value={"results": [], "notices": []}),
            patch.object(academic_search, "_search_arxiv", return_value={"results": [], "notices": []}),
            patch.object(academic_search, "_search_crossref", return_value={"results": [], "notices": []}),
            patch.object(academic_search, "_search_google_scholar") as scholar,
        ):
            academic_search.search_academic("query", max_results=3)

        scholar.assert_not_called()

    def test_google_scholar_can_be_enabled_explicitly(self):
        with (
            patch.object(academic_search, "_search_openalex", return_value={"results": [], "notices": []}),
            patch.object(academic_search, "_search_semantic_scholar", return_value={"results": [], "notices": []}),
            patch.object(academic_search, "_search_arxiv", return_value={"results": [], "notices": []}),
            patch.object(academic_search, "_search_crossref", return_value={"results": [], "notices": []}),
            patch.object(academic_search, "_search_google_scholar", return_value={"results": [], "notices": []}) as scholar,
        ):
            academic_search.search_academic(
                "query",
                max_results=3,
                include_google_scholar=True,
            )

        scholar.assert_called_once()


if __name__ == "__main__":
    unittest.main()
