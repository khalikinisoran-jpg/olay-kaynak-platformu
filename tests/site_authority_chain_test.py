"""Authority Chain visual contract (site/) — read-only static-content test.

Regression guard for the icon+label gluing defect: the chain label must
never be separated from its icon letter by flexbox `gap` alone. Engines
without flex-gap support (older Safari/Chrome/Firefox, preview
renderers) ignore `gap`, which rendered the icon letter flush against
the label ("AAgent" / "RRisk" / "PPolicy"). Separation must come from
explicit, universally-supported margins so the layout is identical in
every engine.

Scope: site/index.html + site/style.css only. No runtime/browser test.
"""
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SITE = REPO / "site"

EXPECTED_NODES = [
    ("A", "Agent"),
    ("\u2192", "Proposal"),
    ("R", "Risk"),
    ("P", "Policy"),
    ("\u2713", "Approval"),
    ("#", "Fingerprint"),
    ("E", "Execute"),
    ("V", "Verify"),
    ("\u2261", "Evidence"),
]

NODE_RE = re.compile(
    r'<li class="chain-node[^"]*">\s*'
    r'<span class="chain-icon[^"]*"[^>]*>(?P<icon>.*?)</span>\s*'
    r'<span class="chain-name">(?P<name>.*?)</span>',
    re.S,
)


def _html():
    return (SITE / "index.html").read_text(encoding="utf-8")


def _css():
    return (SITE / "style.css").read_text(encoding="utf-8")


def _blocks(selector_re):
    return [m.group(1) for m in re.finditer(selector_re, _css(), re.S)]


def _bottom_margin_px(block):
    """Resolve the used bottom margin (px) of a CSS rule block."""
    m = re.search(r"margin-bottom\s*:\s*(-?[\d.]+)px", block)
    if m:
        return float(m.group(1))
    m = re.search(r"margin\s*:\s*([^;]+);", block)
    if not m:
        return 0.0
    parts = m.group(1).split()
    if len(parts) == 1:
        value = parts[0]
    elif len(parts) == 2:
        value = parts[0]
    elif len(parts) in (3, 4):
        value = parts[2]
    else:
        return 0.0
    vm = re.match(r"(-?[\d.]+)px$", value)
    return float(vm.group(1)) if vm else 0.0


def test_chain_has_nine_nodes_with_exact_labels_and_separate_icon():
    nodes = NODE_RE.findall(_html())
    got = [(re.sub(r"<[^>]+>", "", icon).strip(),
            re.sub(r"<[^>]+>", "", name).strip()) for icon, name in nodes]
    assert got == EXPECTED_NODES, f"unexpected chain nodes: {got}"


def test_icon_and_label_are_separate_whitespace_isolated_elements():
    """Markup-level guard: icon span and label span are never concatenated."""
    html = _html()
    for m in NODE_RE.finditer(html):
        # nothing but whitespace may sit between the icon span and the label
        assert m.group(0).count("</span>") >= 1
        gap_text = m.group(0).split("</span>", 1)[1]
        gap_text = gap_text.split('<span class="chain-name">', 1)[0]
        assert gap_text.strip() == "", f"markup glued before label: {gap_text!r}"
        name_text = re.sub(r"<[^>]+>", "", m.group("name")).strip()
        assert name_text in [n for _, n in EXPECTED_NODES], (
            f"label altered (icon char baked in?): {name_text!r}"
        )



def test_icon_label_separation_uses_margins_not_flex_gap():
    icon_blocks = _blocks(r"\.chain-icon\s*\{([^}]*)\}")
    name_blocks = _blocks(r"\.chain-name\s*\{([^}]*)\}")
    assert icon_blocks, ".chain-icon rule missing from style.css"
    assert name_blocks, ".chain-name rule missing from style.css"
    for block in icon_blocks:
        assert _bottom_margin_px(block) > 0, \
            ".chain-icon needs an explicit non-zero margin-bottom"
    for block in name_blocks:
        assert _bottom_margin_px(block) > 0, \
            ".chain-name needs an explicit non-zero margin-bottom"


def test_chain_node_does_not_depend_on_flex_gap():
    node_blocks = _blocks(r"\.chain-node\s*\{([^}]*)\}")
    assert node_blocks, ".chain-node rule missing from style.css"
    for block in node_blocks:
        assert not re.search(r"(^|[^-])gap\s*:", block), (
            ".chain-node must not use `gap` as its spacing mechanism "
            "(breaks on engines without flex-gap support)"
        )


def test_chain_spacing_is_uniform_six_pixels():
    expected = "6px"
    for selector in (r"\.chain-icon", r"\.chain-name"):
        blocks = _blocks(selector + r"\s*\{([^}]*)\}")
        for block in blocks:
            assert _bottom_margin_px(block) == 6.0, (
                f"{selector} spacing changed: expected {expected}"
            )
