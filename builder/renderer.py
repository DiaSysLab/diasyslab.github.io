import json
import markdown
import re
import urllib.parse
from datetime import datetime
from jinja2 import Environment, PackageLoader, Markup, select_autoescape

def init_env():
    global env
    env = Environment(
        loader=PackageLoader('builder', 'templates'),
        autoescape=select_autoescape(['html', 'xml'])
    )
    # 'nl2br' turns a single line break in the sheet cell (Alt+Enter) into a
    # visible <br>, instead of collapsing it into a space like plain Markdown
    # does (a blank line is still needed for a new paragraph).
    md = markdown.Markdown(extensions=['meta', 'nl2br'])

    # Every link Markdown produces with an http(s):// href is external (a
    # relative "/path" or "#anchor" or "mailto:" link stays untouched), so
    # send it to a new tab. This also catches a raw <a href="http...">
    # someone typed directly, since Markdown passes raw HTML through as-is.
    external_link_re = re.compile(r'<a href="(https?://[^"]*)"')
    def open_external_links_in_new_tab(html):
        return external_link_re.sub(r'<a target="_blank" rel="noopener noreferrer" href="\1"', html)

    env.filters['markdown'] = lambda text: Markup(open_external_links_in_new_tab(md.reset().convert(text or '')))

    # Strips a leading '#'..'######' (an ATX heading marker) from the start
    # of any line before rendering 'markdown_inline' text. That text already
    # sits inside a heading element (a title), so honoring '#' there would
    # nest another <h1-6> inside it — mangling spacing/line-height instead of
    # just making it bold, which is what someone typing '#' usually wants.
    heading_marker_re = re.compile(r'(?m)^#{1,6}\s*')

    def markdown_inline(text):
        # Render Markdown but drop a single wrapping <p></p> so the result can
        # sit inside an inline context such as a heading.
        text = heading_marker_re.sub('', text or '')
        html = md.reset().convert(text)
        if html[:3] == '<p>' and html[-4:] == '</p>' and html.count('<p>') == 1:
            html = html[3:-4]
        return Markup(open_external_links_in_new_tab(html))
    env.filters['markdown_inline'] = markdown_inline

    def markdown_links(text):
        # A "links" field (Paper/News/Code buttons) is meant to flow as a
        # row of inline buttons, one link per line just for readability in
        # the sheet — so, unlike 'markdown', collapse a single line break
        # back into a space rather than a <br> (a blank line still starts a
        # new paragraph).
        text = re.sub(r'(?<!\n)\n(?!\n)', ' ', text or '')
        return Markup(open_external_links_in_new_tab(md.reset().convert(text)))
    env.filters['markdown_links'] = markdown_links

    env.filters['jsonify'] = lambda text: json.dumps(text)

def render_index(data):
    template = env.get_template('landing.html')
    max_size = 7
    publications = data['publications']
    landing_research = publications[0]['rows'][:] if publications else []
    if len(landing_research) > max_size:
        landing_research = landing_research[:max_size]
    return template.render(data=data, landing_research=landing_research)

def render_members(data):
    template = env.get_template('members.html')
    return template.render(data=data)

def render_member_page(data, member_page):
    template = env.get_template('members.html')
    return template.render(
        data=data,
        groups=member_page['members'],
        page_title=member_page['title'],
    )

def render_publications(data):
    template = env.get_template('publications.html')
    return template.render(data=data)

def render_research(data):
    template = env.get_template('research.html')
    return template.render(data=data)

def render_links(data):
    template = env.get_template('links.html')
    today = datetime.today()
    for group in data['links']:
        for link in group['rows']:
            if link['query']:
                months = 'jan;feb;mar;apr;may;jun;jul;aug;sep;oct;nov;dec'.split(';')
                try:
                    event_month_num = months.index(link['event_month'][:3].lower()) + 1
                    link['show_this_year'] = today.month <= event_month_num
                    link['show_next_year'] = today.month >= event_month_num - 5
                except ValueError:
                    link['show_this_year'] = True
                    link['show_next_year'] = True
                link['this_year_url'] = 'http://www.google.com/search?q=%s&btnI' % urllib.parse.quote(link['query'].replace(r'{{year}}', str(today.year)))
                link['next_year_url'] = 'http://www.google.com/search?q=%s&btnI' % urllib.parse.quote(link['query'].replace(r'{{year}}', str(today.year + 1)))
                link['this_year_label'] = link['query'].replace(r'{{year}}', str(today.year))
                link['next_year_label'] = link['query'].replace(r'{{year}}', str(today.year + 1))                
                
    return template.render(data=data)

def render_contact(data):
    template = env.get_template('contact.html')
    return template.render(data=data)

def render_gallery(data):
    template = env.get_template('gallery.html')
    return template.render(data=data)

def render_page(data, page):
    template = env.get_template('page.html')
    return template.render(data=data, title=page['title'], content=page['content'])

def render_redirect(data, redirect):
    template = env.get_template('redirect.html')
    return template.render(data=data, url=redirect['url'])

def render_personal_website(data, website_param):   
    template = env.get_template('personal_website.html')
    return template.render(data=data, website=website_param['website'], contents=website_param['contents'])

init_env()
