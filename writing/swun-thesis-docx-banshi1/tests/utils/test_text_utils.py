"""Tests for text_utils module."""
import pytest
from scripts.utils.text_utils import normalize_chinese_double_quotes, preprocess_latex

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


def test_normalize_chinese_double_quotes_converts_ascii_quotes():
    input_text = '本章设计"车辆--RSU--云"三层委托架构。'
    expected = "本章设计\u201c车辆--RSU--云\u201d三层委托架构。"
    assert normalize_chinese_double_quotes(input_text) == expected


def test_normalize_chinese_double_quotes_repairs_malformed_right_quotes():
    input_text = "本章进一步强调\u201c车辆提交、RSU共识、云端索引\u201d的职责边界。"
    expected = "本章进一步强调\u201c车辆提交、RSU共识、云端索引\u201d的职责边界。"
    assert normalize_chinese_double_quotes(input_text) == expected


def test_normalize_chinese_double_quotes_converts_ascii_quotes_around_english_term():
    input_text = '本文称"LightDAG"为基础协议。'
    expected = "本文称\u201cLightDAG\u201d为基础协议。"
    assert normalize_chinese_double_quotes(input_text) == expected


def test_normalize_chinese_double_quotes_keeps_plain_english_quotes():
    input_text = 'This keeps "quoted text" unchanged.'
    assert normalize_chinese_double_quotes(input_text) == input_text
