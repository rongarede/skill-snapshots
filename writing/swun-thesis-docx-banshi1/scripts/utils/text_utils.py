"""Text processing utilities for LaTeX."""
import re

def preprocess_latex(s: str) -> str:
    """Preprocess LaTeX source for pandoc conversion.

    Args:
        s: LaTeX source string

    Returns:
        Preprocessed LaTeX string
    """
    # Pandoc LaTeX reader doesn't recognize \\< escape sequence
    s = s.replace("\\<", "<")

    # Let citeproc generate the references section
    s = re.sub(
        r"\\printbibliography\s*(\[[^\]]*\])?",
        "",
        s,
        flags=re.MULTILINE,
    )

    # Pandoc may drop titlepage env
    s = s.replace("\\begin{titlepage}", "")
    s = s.replace("\\end{titlepage}", "")

    # ulem's \\ul can get dropped
    s = re.sub(r"\\ul\{[^}]*\}", "__________", s)

    return s
