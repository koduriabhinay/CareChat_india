from carechat.knowledge import KnowledgeBase, chunk_text


def test_chunking_respects_limit():
    text = "\n\n".join(["word " * 100] * 10)
    chunks = chunk_text(text, max_chars=1200)
    assert len(chunks) > 1
    assert all(len(c) <= 1200 for c in chunks)


def test_search_ranks_matching_passage(tmp_path):
    kb = KnowledgeBase(str(tmp_path / "kb.db"))
    kb.add_document("Test A", "https://medlineplus.gov/a", "The hemoglobin A1c test measures average blood sugar.")
    kb.add_document("Test B", "https://medlineplus.gov/b", "A lipid panel measures cholesterol.")
    results = kb.search("What does my A1c mean?")
    assert results and results[0].title == "Test A"


def test_search_handles_punctuation_and_empty(tmp_path):
    kb = KnowledgeBase(str(tmp_path / "kb.db"))
    kb.add_document("T", "https://medlineplus.gov/t", "Sodium levels in blood.")
    assert kb.search('what "is" (sodium)?*')
    assert kb.search("what is it?") == []


def test_reindexing_same_url_replaces(tmp_path):
    kb = KnowledgeBase(str(tmp_path / "kb.db"))
    kb.add_document("T", "https://medlineplus.gov/t", "old text about sodium")
    kb.add_document("T", "https://medlineplus.gov/t", "new text about sodium")
    assert kb.count() == 1
