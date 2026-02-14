from agents.download_agent import file_extension, safe_filename


def test_safe_filename_replaces_special_chars():
    assert safe_filename("a/b:c") == "a_b_c"


def test_file_extension_detects_pdf():
    assert file_extension("https://example.com/a.pdf") == ".pdf"
    assert file_extension("https://example.com/a") == ".html"
