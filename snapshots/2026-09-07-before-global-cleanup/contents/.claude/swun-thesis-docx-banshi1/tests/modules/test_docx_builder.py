"""Tests for docx_builder."""
from scripts.modules import docx_builder


def test_preprocess_latex_normalizes_chinese_double_quotes():
    input_text = '本章设计"车辆--RSU--云"三层委托架构。'
    expected = "本章设计\u201c车辆--RSU--云\u201d三层委托架构。"
    assert docx_builder._preprocess_latex(input_text) == expected


def test_preprocess_latex_normalizes_ascii_quotes_around_english_term_in_chinese_context():
    input_text = '本文称"LightDAG"为基础协议。'
    expected = "本文称\u201cLightDAG\u201d为基础协议。"
    assert docx_builder._preprocess_latex(input_text) == expected
