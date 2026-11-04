"""V1.1 report navigation, explanations, and evidence distinctions."""
from html.parser import HTMLParser

from branchcheck.analyzer import analyze
from branchcheck.loader import validate_story
from branchcheck.models import Limits
from branchcheck.reports import render_html, render_text


class LinksAndIds(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ids = set()
        self.hrefs = []
        self.tags = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        self.tags.append((tag, attributes))
        if attributes.get('id'):
            self.ids.add(attributes['id'])
        if attributes.get('href'):
            self.hrefs.append(attributes['href'])


def diagnostic_story():
    attack = '<script>alert("report & pointer")</script>'
    return validate_story({
        'schema_version': 1,
        'title': attack,
        'start': 'start',
        'variables': {'a': False, 'b': False},
        'nodes': [
            {
                'id': 'start',
                'title': attack,
                'choices': [{
                    'id': 'blocked',
                    'text': attack,
                    'target': 'end',
                    'condition': {'all': [
                        {'var': 'a', 'eq': True},
                        {'any': [
                            {'var': 'b', 'eq': True},
                            {'not': {'var': 'b', 'eq': False}},
                        ]},
                    ]},
                    'effects': {'a': True},
                }],
            },
            {'id': 'end', 'title': '结局', 'ending': True},
        ],
    })


def test_html_directory_links_target_real_stable_anchors():
    html = render_html(analyze(diagnostic_story()))
    parser = LinksAndIds()
    parser.feed(html)

    assert 'diagnostic-1' in parser.ids
    assert {'node-1', 'node-2'} <= parser.ids
    fragment_links = [href[1:] for href in parser.hrefs if href.startswith('#')]
    assert fragment_links
    assert all(fragment in parser.ids for fragment in fragment_links)
    assert 'href="#diagnostic-1"' in html
    assert 'id="node-1"' in html


def test_html_renders_explanations_sources_and_static_variable_clues():
    report = analyze(diagnostic_story())
    html = render_html(report)
    text = render_text(report)

    assert '具体状态下的条件解释' in html
    assert '全部满足' in html
    assert '任一满足' in html
    assert '取反' in html
    assert '变量赋值位置线索' in html
    assert '源节点：可达' in html
    assert '完整搜索中未观察到触发' in html
    assert '/nodes/0/choices/0/condition' in html
    assert '/nodes/0/choices/0/effects/a' in html
    assert '主要源位置：/nodes/0' in text
    assert '根结果：不满足' in text
    assert '静态写入 /nodes/0/choices/0/effects/a' in text
    assert '代表路径不等同于全部路径' in html


def test_html_escapes_all_new_fields_and_has_no_external_runtime():
    attack = '<script>alert("report & pointer")</script>'
    html = render_html(analyze(diagnostic_story()))
    parser = LinksAndIds()
    parser.feed(html)

    assert attack not in html
    assert '&lt;script&gt;alert(&quot;report &amp; pointer&quot;)&lt;/script&gt;' in html
    assert all(tag not in {'script', 'iframe', 'img', 'link'} for tag, _ in parser.tags)
    assert all(not any(name.startswith('on') for name in attrs) for _, attrs in parser.tags)
    assert all(not href.startswith(('http:', 'https:', '//')) for href in parser.hrefs)
    assert "default-src 'none'; style-src 'unsafe-inline'" in html


def test_incomplete_report_keeps_warning_visible_and_unknown_explicit():
    story = validate_story({
        'schema_version': 1,
        'title': '达到上限',
        'start': 'start',
        'variables': {},
        'nodes': [
            {'id': 'start', 'title': '起点', 'choices': [
                {'id': 'go', 'text': '继续', 'target': 'middle'},
            ]},
            {'id': 'middle', 'title': '中间', 'choices': [
                {'id': 'finish', 'text': '结束', 'target': 'end'},
            ]},
            {'id': 'end', 'title': '结局', 'ending': True},
        ],
    })
    report = analyze(story, Limits(max_states=1))
    html = render_html(report)
    text = render_text(report)

    assert report['overall_status'] == 'incomplete'
    assert 'class="incomplete-banner"' in html
    assert '未访问节点和未观察到的选择保持未知' in html
    assert '分析未完成' in text
    assert '保持未知' in text
