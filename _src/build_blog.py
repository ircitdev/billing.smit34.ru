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
            out.append('<li>%s</li>' % inline(m.group(2)))
            i += 1
            continue

        if stripped.startswith('- '):
            if lst != ('ul',):
                close_list()
                out.append('<ul>')
                lst = ('ul',)
            out.append('<li>%s</li>' % inline(stripped[2:]))
            i += 1
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
    meta['body'] = md_to_html(m.group(2).strip())
    for need in ('title', 'date', 'tag', 'summary'):
        if need not in meta:
            raise SystemExit('в %s нет поля %s' % (path, need))
    return meta


# ─────────────────────────── шаблоны ───────────────────────────

HEAD = u'''<!DOCTYPE html>
<html lang="ru" data-theme="dark">
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
<link rel="stylesheet" href="/blog/blog.css">
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
</body>
</html>
'''

CTA = u'''<div class="bcta">
  <h3>Посмотреть платформу в работе</h3>
  <p>Демо-доступ с реальными данными, презентация для руководства и ответы на вопросы — без обязательств.</p>
  <a href="/#demo">Запросить демо →</a>
</div>'''


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


def post_page(p, year):
    return (HEAD.format(title=esc(p['title']) + ' — блог СмИТ Биллинг',
                        desc=esc(p['summary']),
                        canonical='%s/blog/%s' % (SITE, p['slug']),
                        ogtype='article', blogcur=' aria-current="page"',
                        ogimage=og_image(p['cover'])) +
            u'''<main class="bpost">
  <div class="container narrow">
    <a class="bback" href="/blog/">← Все статьи</a>
    <div><span class="btag">{tag}</span></div>
    <h1>{title}</h1>
    <div class="bmeta"><time datetime="{iso}">{date}</time> · {read}</div>
    {cover}
    {body}
    {cta}
  </div>
</main>
'''.format(tag=esc(p['tag']), title=esc(p['title']), iso=p['date'],
           date=human_date(p['date']), read=p.get('read', '5 минут'),
           cover=cover_img(p['cover'], 'bpost-cover'),
           body=p['body'], cta=CTA) +
            FOOT.format(year=year))


def card(p, tag='article'):
    return u'''      <a class="bcard" href="/blog/{slug}">
        {cover}
        <div class="bcard-meta"><span class="btag">{tag}</span><time datetime="{iso}">{date}</time></div>
        <h3>{title}</h3>
        <p>{summary}</p>
        <span class="bcard-more">Читать →</span>
      </a>'''.format(slug=p['slug'], tag=esc(p['tag']), iso=p['date'],
                     cover=cover_img(p['cover'], 'bcard-cover'),
                     date=human_date(p['date']), title=esc(p['title']),
                     summary=esc(p['summary']))


def index_page(posts, year):
    return (HEAD.format(title='Блог — СмИТ Биллинг',
                        desc='Статьи о работе интернет-провайдера: биллинг, поддержка, продажи, '
                             'оборудование и автоматизация.',
                        canonical=SITE + '/blog/', ogtype='website',
                        blogcur=' aria-current="page"',
                        ogimage=og_image(posts[0]['cover'] if posts else '')) +
            u'''<main>
  <div class="container">
    <div class="bhead">
      <span class="bkicker">Блог</span>
      <h1>Как устроена работа провайдера</h1>
      <p>Разбираем задачи, с которыми оператор связи сталкивается каждый день: заявки и подключения,
         деньги на счетах, обращения абонентов, оборудование у монтажников. Без общих слов — на том,
         как это работает в СмИТ Биллинге.</p>
    </div>
    <div class="bgrid">
{cards}
    </div>
  </div>
</main>
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
        io.open(out, 'w', encoding='utf-8').write(post_page(p, year))
        print('  пост: /blog/%s' % p['slug'])
    io.open(os.path.join(BLOG_DIR, 'index.html'), 'w', encoding='utf-8').write(index_page(posts, year))
    print('  список: /blog/ (%d статей)' % len(posts))

    patch_home(posts)
    patch_sitemap(posts)


if __name__ == '__main__':
    main()
