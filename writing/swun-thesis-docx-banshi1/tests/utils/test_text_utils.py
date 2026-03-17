"""Tests for text_utils module."""
import pytest
from scripts.utils.text_utils import normalize_chinese_double_quotes, normalize_chinese_spaces, preprocess_latex

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


class TestNormalizeChineseSpaces:
    """normalize_chinese_spaces 测试。"""

    def test_empty_string(self):
        assert normalize_chinese_spaces("") == ""

    def test_no_spaces(self):
        assert normalize_chinese_spaces("你好世界") == "你好世界"

    def test_pure_english(self):
        assert normalize_chinese_spaces("hello world test") == "hello world test"

    def test_rule1_punct_after_space(self):
        """中文标点后的空格应删除。"""
        assert normalize_chinese_spaces("你好。 世界") == "你好。世界"
        assert normalize_chinese_spaces("你好， 世界") == "你好，世界"
        assert normalize_chinese_spaces("你好； 世界") == "你好；世界"
        assert normalize_chinese_spaces("你好： 世界") == "你好：世界"

    def test_rule1_curly_quote_after_space(self):
        """弯引号后的空格应删除。"""
        assert normalize_chinese_spaces("\u201d 世界") == "\u201d世界"
        assert normalize_chinese_spaces("\u2019 世界") == "\u2019世界"

    def test_rule2_en_to_cn(self):
        """英文字符后 + 中文字符前的空格应删除。"""
        assert normalize_chinese_spaces("LightDAG 共识") == "LightDAG共识"
        assert normalize_chinese_spaces("V2V） 与") == "V2V）与"

    def test_rule3_cn_to_en(self):
        """中文字符后 + 英文字母前的空格应删除。"""
        assert normalize_chinese_spaces("链式 HotStuff") == "链式HotStuff"
        assert normalize_chinese_spaces("面向 LightDAG") == "面向LightDAG"

    def test_preserve_date_format(self):
        """日期格式中的空格应保留。"""
        assert normalize_chinese_spaces("2026 年 6 月 10 日") == "2026 年 6 月 10 日"

    def test_preserve_english_spaces(self):
        """英文单词间的空格应保留。"""
        assert normalize_chinese_spaces("Ad Hoc Network") == "Ad Hoc Network"

    def test_preserve_cn_cn_spaces(self):
        """纯中文间的空格应保留（不触发任何规则）。"""
        assert normalize_chinese_spaces("你好 世界") == "你好 世界"

    def test_multiple_spaces(self):
        """连续多个空格应按规则处理。"""
        assert normalize_chinese_spaces("你好。  世界") == "你好。世界"
