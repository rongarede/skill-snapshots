"""Tests for text_utils module."""
import pytest
from scripts.utils.text_utils import preprocess_latex

def test_preprocess_latex_replaces_backslash_lt():
    """Test \\< replacement."""
    input_text = "Some text \\< more text"
    expected = "Some text < more text"
    assert preprocess_latex(input_text) == expected

def test_preprocess_latex_removes_printbibliography():
    """Test \\printbibliography removal."""
    input_text = "Text\n\\printbibliography[title=References]\nMore"
    result = preprocess_latex(input_text)
    assert "\\printbibliography" not in result

def test_preprocess_latex_removes_titlepage():
    """Test titlepage environment removal."""
    input_text = "\\begin{titlepage}\nContent\n\\end{titlepage}"
    result = preprocess_latex(input_text)
    assert "titlepage" not in result
    assert "Content" in result

def test_preprocess_latex_replaces_ul():
    """Test \\ul replacement."""
    input_text = "Name: \\ul{　　　　　}"
    result = preprocess_latex(input_text)
    assert "__________" in result
    assert "\\ul" not in result
