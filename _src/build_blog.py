# -*- coding: utf-8 -*-
"""Сборка блога billing.smit34.ru из markdown-файлов.

Что делает:
  1. читает `_src/posts/*.md` (заголовок в YAML-шапке, текст ниже);
  2. пишет `blog/<slug>.html` — страницу поста;
  3. пишет `blog/index.html` — список всех постов;
  4. вставляет три свежих поста в главную между маркерами
     `<!-- BLOG:START -->` и `<!-- BLOG:END -->`;
  5. дописывает адреса блога в `sitemap.xml`.

Запуск из корня сайта (там, где index.html):

    python _src/build_blog.py

Markdown понимается в объёме, который нужен постам: заголовки ##/###, списки,
цитаты, таблицы, ссылки, **жирный**, `код`. Внешних библиотек нет намеренно —
скрипт должен работать и на сервере, где ставить пакеты некому.
"""
import glob
import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POSTS_DIR = os.path.join(ROOT, '_src', 'posts')
BLOG_DIR = os.path.join(ROOT, 'blog')
SITE = 'https://billing.smit34.ru'
HOME_LIMIT = 3          # сколько постов показываем на главной


# ─────────────────────────── markdown ───────────────────────────

def esc(t):
    return (t.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'))


def inline(t):
    """Жирный, код, ссылки — внутри строки."""
    t = esc(t)
    t = re.sub(r'`([^`]+)`', r'<code>\1</code>', t)
    t = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', t)
    t = re.sub(r'\[([^\]]+)\]\(([^)]+)\)',
               r'<a href="\2" rel="noopener">\1</a>', t)
    return t


ITEM_BREAK = re.compile(r'^(#{2,3}\s|-\s|\d+\.\s|>\s|\|)')


def item_text(lines, i, first):
    """Пункт списка вместе с его продолжением на следующих строках.

    Без этого перенос внутри пункта вываливался отдельным абзацем под списком.
    """
    parts = [first]
    i += 1
    while i < len(lines) and lines[i].strip() and not ITEM_BREAK.match(lines[i].strip()):
        parts.append(lines[i].strip())
        i += 1
    return ' '.join(parts), i


def md_to_html(md):
    out, lst, table = [], None, None

    def close_list():
        if lst:
            out.append('</%s>' % lst[0])

    def close_table():
        if table:
            out.append('</tbody></table>')

    lines = md.split('\n')
    i = 0
    while i < len(lines):
        ln = lines[i].rstrip()
        stripped = ln.strip()

        # блок в тройных кавычках: mermaid-схема или обычный код
        if stripped.startswith('```'):
            lang = stripped[3:].strip().lower()
            i += 1
            block = []
            while i < len(lines) and not lines[i].strip().startswith('```'):
                block.append(lines[i])
                i += 1
            i += 1
            close_list()
            lst = None
            body = '\n'.join(block)
            if lang == 'mermaid':
                out.append('<div class="bmermaid"><pre class="mermaid">%s</pre></div>' % esc(body))
            else:
                out.append('<pre class="bcode"><code>%s</code></pre>' % esc(body))
            continue

        # таблица: строка с | и следующая из дефисов
        if stripped.startswith('|') and i + 1 < len(lines) and re.match(r'^\|[\s\-:|]+\|$', lines[i + 1].strip()):
            cells = [c.strip() for c in stripped.strip('|').split('|')]
            out.append('<table><thead><tr>' +
                       ''.join('<th>%s</th>' % inline(c) for c in cells) +
                       '</tr></thead><tbody>')
            table = True
            i += 2
            continue
        if table:
            if stripped.startswith('|'):
                cells = [c.strip() for c in stripped.strip('|').split('|')]
                out.append('<tr>' + ''.join('<td>%s</td>' % inline(c) for c in cells) + '</tr>')
                i += 1
                continue
            close_table()
            table = None

        if not stripped:
            close_list()
            lst = None
            i += 1
            continue

        m = re.match(r'^(#{2,3})\s+(.*)$', stripped)
        if m:
            close_list()
            lst = None
            level = len(m.group(1))
            out.append('<h%d>%s</h%d>' % (level, inline(m.group(2)), level))
            i += 1
            continue

        if stripped.startswith('> '):
            close_list()
            lst = None
            quote = []
            while i < len(lines) and lines[i].strip().startswith('> '):
                quote.append(lines[i].strip()[2:])
                i += 1
            out.append('<blockquote>%s</blockquote>' % inline(' '.join(quote)))
            continue

        m = re.match(r'^(\d+)\.\s+(.*)$', stripped)
        if m:
            if lst != ('ol',):
                close_list()
                out.append('<ol>')
                lst = ('ol',)
            text, i = item_text(lines, i, m.group(2))
            out.append('<li>%s</li>' % inline(text))
            continue

        if stripped.startswith('- '):
            if lst != ('ul',):
                close_list()
                out.append('<ul>')
                lst = ('ul',)
            text, i = item_text(lines, i, stripped[2:])
            out.append('<li>%s</li>' % inline(text))
            continue

        # абзац: собираем до пустой строки
        para = [stripped]
        i += 1
        while i < len(lines) and lines[i].strip() and not re.match(r'^(#{2,3}\s|-\s|\d+\.\s|>\s|\|)', lines[i].strip()):
            para.append(lines[i].strip())
            i += 1
        close_list()
        lst = None
        out.append('<p>%s</p>' % inline(' '.join(para)))

    close_list()
    close_table()
    return '\n'.join(out)


# ─────────────────────────── посты ───────────────────────────

MONTHS = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
          'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря']


def human_date(iso):
    y, m, d = iso.split('-')
    return '%d %s %s' % (int(d), MONTHS[int(m) - 1], y)


def read_post(path):
    raw = io.open(path, encoding='utf-8').read()
    m = re.match(r'^---\n(.*?)\n---\n(.*)$', raw, re.S)
    if not m:
        raise SystemExit('нет YAML-шапки: ' + path)
    meta = {}
    for line in m.group(1).split('\n'):
        if ':' in line:
            k, v = line.split(':', 1)
            meta[k.strip()] = v.strip().strip('"')
    meta['slug'] = os.path.splitext(os.path.basename(path))[0]
    if 'cover' not in meta:
        jpg = os.path.join(BLOG_DIR, 'covers', meta['slug'] + '.jpg')
        meta['cover'] = '/blog/covers/%s.jpg' % meta['slug'] if os.path.isfile(jpg) else ''
    meta['tags'] = [t.strip() for t in meta.get('tags', '').split(',') if t.strip()]
    meta['body'] = md_to_html(m.group(2).strip())
    for need in ('title', 'date', 'tag', 'summary'):
        if need not in meta:
            raise SystemExit('в %s нет поля %s' % (path, need))
    return meta


# ─────────────────────────── шаблоны ───────────────────────────

HEAD = u'''<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="description" content="{desc}">
<link rel="canonical" href="{canonical}">
<meta property="og:type" content="{ogtype}">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{desc}">
<meta property="og:url" content="{canonical}">
<meta property="og:site_name" content="СмИТ Биллинг">
{ogimage}
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="stylesheet" href="/blog/blog.css?v={cssver}">
<script>
  // тема общая с главной: ключ billing-theme, светлая — атрибутом data-theme
  (function () {{
    try {{
      if (localStorage.getItem('billing-theme') === 'light') {{
        document.documentElement.setAttribute('data-theme', 'light');
      }}
    }} catch (e) {{}}
  }})();
</script>
</head>
<body>
<header class="bh">
  <div class="bh-inner">
    <a class="bh-logo" href="/"><span class="bh-mark">C</span> СмИТ Биллинг</a>
    <nav class="bh-nav">
      <a href="/#features">Возможности</a>
      <a href="/#modules">Модули</a>
      <a href="/#pricing">Тарифы</a>
      <a href="/blog/"{blogcur}>Блог</a>
      <a href="/#demo" class="bh-cta">Запросить демо</a>
      <button class="bh-theme" id="bh-theme" type="button" aria-label="Переключить тему">
        <span class="bh-sun">☀</span><span class="bh-moon">☾</span>
      </button>
    </nav>
  </div>
</header>
'''

FOOT = u'''<footer class="bfoot">
  <div class="container">
    <span>© {year} СмИТ Биллинг — платформа для операторов связи</span>
    <a class="sep" href="/">На главную</a>
    <a href="https://docs.billing.smit34.ru" target="_blank" rel="noopener">Документация</a>
  </div>
</footer>
<script>
  (function () {{
    var btn = document.getElementById('bh-theme');
    if (!btn) return;
    btn.addEventListener('click', function () {{
      var root = document.documentElement;
      var light = root.getAttribute('data-theme') === 'light';
      if (light) {{ root.removeAttribute('data-theme'); }} else {{ root.setAttribute('data-theme', 'light'); }}
      try {{ localStorage.setItem('billing-theme', light ? 'dark' : 'light'); }} catch (e) {{}}
    }});
  }})();
</script>
</body>
</html>
'''

CTA = u'''<div class="bcta">
  <h3>Посмотреть платформу в работе</h3>
  <p>Демо-доступ с реальными данными, презентация для руководства и ответы на вопросы — без обязательств.</p>
  <a href="/#demo">Запросить демо →</a>
</div>'''


def css_version():
    css = os.path.join(BLOG_DIR, 'blog.css')
    return str(int(os.path.getmtime(css))) if os.path.isfile(css) else '1'


def cover_img(cover, cls):
    """Тег обложки: пустая строка, если картинки у поста нет."""
    if not cover:
        return ''
    return ('<img class="%s" src="%s" alt="" loading="lazy" width="1600" height="900">'
            % (cls, cover))


def og_image(cover):
    if not cover:
        return ''
    return ('<meta property="og:image" content="%s%s">' % (SITE, cover) +
            '\n<meta name="twitter:card" content="summary_large_image">')


def hashtags(tags):
    """Хештеги под статьёй: ведут в список, отфильтрованный по тегу."""
    if not tags:
        return ''
    items = ''.join('<a class="bhash" href="/blog/?tag=%s">#%s</a>'
                    % (esc(t), esc(t.replace(' ', '_'))) for t in tags)
    return '<div class="bhashes">%s</div>' % items


def related(p, posts, limit=2):
    """«Читайте также»: сначала статьи с общими тегами, потом просто свежие."""
    mine = set(p['tags'])
    others = [o for o in posts if o['slug'] != p['slug']]
    others.sort(key=lambda o: (-len(mine & set(o['tags'])), o['date']), reverse=False)
    others.sort(key=lambda o: len(mine & set(o['tags'])), reverse=True)
    picked = others[:limit]
    if not picked:
        return ''
    return (u'''  <section class="brelated">
    <h2>Читайте также</h2>
    <div class="brel-grid">
%s
    </div>
  </section>''' % '\n'.join(card(o) for o in picked))


MERMAID = u'''<script type="module">
  import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs';
  // тема под палитру сайта; схема не должна спорить с текстом статьи
  mermaid.initialize({
    startOnLoad: true,
    theme: 'base',
    fontFamily: 'Inter, system-ui, sans-serif',
    themeVariables: {
      background: 'transparent',
      primaryColor: '#0f2a22',
      primaryTextColor: '#e2e8f0',
      primaryBorderColor: '#10b981',
      lineColor: '#2dd4bf',
      secondaryColor: '#132030',
      tertiaryColor: '#0b1622',
      fontSize: '17px'
    },
    flowchart: { curve: 'basis', useMaxWidth: false, nodeSpacing: 34, rankSpacing: 46 }
  });
  // при смене темы схему нужно перерисовать: цвета зашиты в SVG
  var root = document.documentElement;
  new MutationObserver(function () {
    var light = root.getAttribute('data-theme') === 'light';
    document.querySelectorAll('pre.mermaid').forEach(function (el) {
      if (!el.dataset.src) el.dataset.src = el.textContent;
      el.removeAttribute('data-processed');
      el.innerHTML = el.dataset.src;
    });
    mermaid.initialize({
      startOnLoad: false, theme: 'base', fontFamily: 'Inter, system-ui, sans-serif',
      themeVariables: light
        ? { background: '#ffffff', primaryColor: '#e8f6f0', primaryTextColor: '#0f172a',
            primaryBorderColor: '#0f9d76', lineColor: '#0f9d76', secondaryColor: '#f1f5f9',
            tertiaryColor: '#f8fafc', fontSize: '17px' }
        : { background: 'transparent', primaryColor: '#0f2a22', primaryTextColor: '#e2e8f0',
            primaryBorderColor: '#10b981', lineColor: '#2dd4bf', secondaryColor: '#132030',
            tertiaryColor: '#0b1622', fontSize: '17px' },
      flowchart: { curve: 'basis', useMaxWidth: false, nodeSpacing: 34, rankSpacing: 46 }
    });
    mermaid.run({ querySelector: 'pre.mermaid' });
  }).observe(root, { attributes: true, attributeFilter: ['data-theme'] });
</script>'''


def mermaid_script(body):
    """Библиотека подключается только к статьям, где схема действительно есть."""
    return MERMAID if 'class="mermaid"' in body else ''


def post_page(p, year, posts):
    return (HEAD.format(title=esc(p['title']) + ' — блог СмИТ Биллинг',
                        desc=esc(p['summary']),
                        canonical='%s/blog/%s' % (SITE, p['slug']),
                        ogtype='article', blogcur=' aria-current="page"',
                        ogimage=og_image(p['cover']), cssver=css_version()) +
            u'''<main class="bpost">
  <div class="container narrow">
    <a class="bback" href="/blog/">← Все статьи</a>
    <div><span class="btag">{tag}</span></div>
    <h1>{title}</h1>
    <div class="bmeta"><time datetime="{iso}">{date}</time> · {read}</div>
    {cover}
    {body}
    {hashes}
    {cta}
  </div>
  <div class="container">
{rel}
  </div>
</main>
{mermaid}
'''.format(tag=esc(p['tag']), title=esc(p['title']), iso=p['date'],
           date=human_date(p['date']), read=p.get('read', '5 минут'),
           cover=cover_img(p['cover'], 'bpost-cover'),
           body=p['body'], hashes=hashtags(p['tags']), cta=CTA,
           rel=related(p, posts), mermaid=mermaid_script(p['body'])) +
            FOOT.format(year=year))


def card(p, tag='article'):
    return u'''      <a class="bcard" href="/blog/{slug}" data-tags="{tags}">
        {cover}
        <div class="bcard-meta"><span class="btag">{tag}</span><time datetime="{iso}">{date}</time></div>
        <h3>{title}</h3>
        <p>{summary}</p>
        <span class="bcard-more">Читать →</span>
      </a>'''.format(slug=p['slug'], tag=esc(p['tag']), iso=p['date'],
                     tags=esc(','.join(p['tags'])),
                     cover=cover_img(p['cover'], 'bcard-cover'),
                     date=human_date(p['date']), title=esc(p['title']),
                     summary=esc(p['summary']))


def index_page(posts, year):
    return (HEAD.format(title='Блог — СмИТ Биллинг',
                        desc='Статьи о работе интернет-провайдера: биллинг, поддержка, продажи, '
                             'оборудование и автоматизация.',
                        canonical=SITE + '/blog/', ogtype='website',
                        blogcur=' aria-current="page"',
                        ogimage=og_image(posts[0]['cover'] if posts else ''), cssver=css_version()) +
            u'''<main>
  <div class="container">
    <div class="bhead">
      <span class="bkicker">Блог</span>
      <h1>Как устроена работа провайдера</h1>
      <p>Разбираем задачи, с которыми оператор связи сталкивается каждый день: заявки и подключения,
         деньги на счетах, обращения абонентов, оборудование у монтажников. Без общих слов — на том,
         как это работает в СмИТ Биллинге.</p>
    </div>
    <div class="bfilter" id="bfilter" hidden>
      <span>Тег:</span> <strong id="bfilter-name"></strong>
      <a href="/blog/">показать все →</a>
    </div>
    <div class="bgrid" id="bgrid">
{cards}
    </div>
    <p class="bempty" id="bempty" hidden>По этому тегу статей пока нет.</p>
  </div>
</main>
<script>
// ?tag=... — хештег из статьи фильтрует список без перезагрузки данных
(function () {{
  var tag = new URLSearchParams(location.search).get('tag');
  if (!tag) return;
  var shown = 0;
  document.querySelectorAll('#bgrid .bcard').forEach(function (c) {{
    var has = (c.dataset.tags || '').split(',').indexOf(tag) > -1;
    c.hidden = !has;
    if (has) shown++;
  }});
  var bar = document.getElementById('bfilter');
  document.getElementById('bfilter-name').textContent = '#' + tag;
  bar.hidden = false;
  document.getElementById('bempty').hidden = shown > 0;
}})();
</script>
'''.format(cards='\n'.join(card(p) for p in posts)) +
            FOOT.format(year=year))


# ─────────────────────────── главная ───────────────────────────

HOME_SECTION = u'''<!-- BLOG:START -->
<section id="blog" class="blog-section">
  <div class="container">
    <div class="section-badge reveal">Блог</div>
    <h2 class="section-title reveal reveal-delay-1">Как устроена работа провайдера</h2>
    <p class="section-subtitle reveal reveal-delay-2" style="margin:0 auto 32px">Разборы ежедневных задач оператора связи: заявки, деньги, обращения абонентов и оборудование.</p>
    <div class="blog-grid">
{cards}
    </div>
    <div style="text-align:center;margin-top:28px">
      <a href="/blog/" class="btn-secondary">Все статьи →</a>
    </div>
  </div>
</section>
<!-- BLOG:END -->'''

HOME_CARD = u'''      <a class="blog-card reveal" href="/blog/{slug}">
        {cover}
        <div class="blog-card-meta"><span class="blog-tag">{tag}</span><time datetime="{iso}">{date}</time></div>
        <h3>{title}</h3>
        <p>{summary}</p>
        <span class="blog-card-more">Читать →</span>
      </a>'''


def home_section(posts):
    cards = '\n'.join(HOME_CARD.format(slug=p['slug'], tag=esc(p['tag']), iso=p['date'],
                                       cover=cover_img(p['cover'], 'blog-card-cover'),
                                       date=human_date(p['date']), title=esc(p['title']),
                                       summary=esc(p['summary']))
                      for p in posts[:HOME_LIMIT])
    return HOME_SECTION.format(cards=cards)


def patch_home(posts):
    path = os.path.join(ROOT, 'index.html')
    html = io.open(path, encoding='utf-8').read()
    if '<!-- BLOG:START -->' not in html:
        print('  главная: маркеров нет — секция не вставлена (добавьте BLOG:START/END)')
        return
    new = re.sub(r'<!-- BLOG:START -->.*?<!-- BLOG:END -->', lambda _: home_section(posts),
                 html, flags=re.S)
    if new != html:
        io.open(path, 'w', encoding='utf-8').write(new)
        print('  главная: секция обновлена (%d поста)' % min(HOME_LIMIT, len(posts)))
    else:
        print('  главная: без изменений')


def patch_sitemap(posts):
    path = os.path.join(ROOT, 'sitemap.xml')
    if not os.path.isfile(path):
        return
    xml = io.open(path, encoding='utf-8').read()
    xml = re.sub(r'\s*<url>\s*<loc>https://billing\.smit34\.ru/blog/[^<]*</loc>.*?</url>', '', xml, flags=re.S)
    block = ['  <url>\n    <loc>%s/blog/</loc>\n    <lastmod>%s</lastmod>\n'
             '    <changefreq>weekly</changefreq>\n    <priority>0.7</priority>\n  </url>'
             % (SITE, posts[0]['date'])]
    for p in posts:
        block.append('  <url>\n    <loc>%s/blog/%s</loc>\n    <lastmod>%s</lastmod>\n'
                     '    <changefreq>monthly</changefreq>\n    <priority>0.6</priority>\n  </url>'
                     % (SITE, p['slug'], p['date']))
    xml = xml.replace('</urlset>', '\n'.join(block) + '\n</urlset>')
    io.open(path, 'w', encoding='utf-8').write(xml)
    print('  sitemap: %d адресов блога' % (len(posts) + 1))


def main():
    files = sorted(glob.glob(os.path.join(POSTS_DIR, '*.md')))
    if not files:
        raise SystemExit('нет постов в ' + POSTS_DIR)
    posts = sorted((read_post(f) for f in files), key=lambda p: p['date'], reverse=True)
    year = max(p['date'][:4] for p in posts)

    if not os.path.isdir(BLOG_DIR):
        os.makedirs(BLOG_DIR)
    for p in posts:
        out = os.path.join(BLOG_DIR, p['slug'] + '.html')
        io.open(out, 'w', encoding='utf-8').write(post_page(p, year, posts))
        print('  пост: /blog/%s' % p['slug'])
    io.open(os.path.join(BLOG_DIR, 'index.html'), 'w', encoding='utf-8').write(index_page(posts, year))
    print('  список: /blog/ (%d статей)' % len(posts))

    patch_home(posts)
    patch_sitemap(posts)


if __name__ == '__main__':
    main()
