import certifi
import dateutil.parser
import functools
import os
import re
import json
import urllib
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from . import config

SHEETS_URL_BASE = 'https://sheets.googleapis.com/v4/spreadsheets'
DRIVE_FILES_URL = 'https://www.googleapis.com/drive/v3/files'
# The Gallery tab maps an album (title + optional Markdown description) to a
# Google Drive folder; every image in that folder becomes a slide.
GALLERY_RANGE = 'Gallery!A2:C'
# The 'Publications' tab holds the paper list (same layout the 'Research' tab
# used to have); the 'Research' tab is now a research-introduction page.
PUBLICATIONS_RANGE = 'Publications!A2:F'
RESEARCH_RANGE = 'Research!A2:C'
RANGES = [
    'Website!B2:C',
    'Announcements!A2:C',
    'Members!A2:H',
    'Tags!A2:F',
    'Links!A2:G',
    'Pages!A2:C',
    'Redirects!A2:B',
    'Personal!A2:B',
]
PERSONAL_RANGES = [
    'Website!B2:C',
    'Contents!A2:B',
]
MENU_RANGE = 'Menu!A2:C'
# Used when the spreadsheet has no 'Menu' tab yet, so existing sites keep working.
DEFAULT_MENU = [
    {'title': 'Home', 'url': '/', 'children': []},
    {'title': 'Members', 'url': '/members', 'children': []},
    {'title': 'Research', 'url': '/research', 'children': []},
    {'title': 'Links', 'url': '/links', 'children': []},
    {'title': 'Contact', 'url': '/contact', 'children': []},
]
# Any spreadsheet tab named "Members - <Name>" becomes its own member page at
# /members/<slug-of-name>, managed independently from the main Members tab.
MEMBER_PAGE_PREFIX = 'Members - '

def get_doc_id(data_url):
    tokens = data_url.split('/')
    doc_id = ''
    # Use a heuristic method for finding document ID from the URL.
    for token in tokens:
        if re.match(r'[a-zA-Z0-9]+', token) is not None:
            if len(token) > len(doc_id):
                doc_id = token
    return doc_id

def get_drive_folder_id(link):
    link = (link or '').strip()
    if not link:
        return ''
    m = re.search(r'/folders/([a-zA-Z0-9_-]+)', link)
    if m:
        return m.group(1)
    # A bare id, or some other URL form: drop any query string and take the
    # longest path segment.
    link = link.split('?')[0]
    tokens = [t for t in link.split('/') if t]
    return max(tokens, key=len) if tokens else ''

def list_drive_images(folder_id):
    query = "'%s' in parents and mimeType contains 'image/' and trashed = false" % folder_id
    params = urllib.parse.urlencode({
        'q': query,
        'key': config.API_KEY,
        'fields': 'files(id,name)',
        'orderBy': 'name_natural',
        'pageSize': 100,
    })
    url = '%s?%s' % (DRIVE_FILES_URL, params)
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, cafile=certifi.where()) as response:
        data = response.read()
    files = json.loads(data).get('files', [])
    return [{
        'name': f.get('name', ''),
        'url': 'https://drive.google.com/thumbnail?id=%s&sz=w1600' % f['id'],
    } for f in files if f.get('id')]

# Cached for the life of one build: several members/albums commonly share
# the same Drive folder (e.g. all students under "member/student"), and
# without this every one of them would re-list or re-query that same
# folder from scratch.
@functools.lru_cache(maxsize=None)
def list_drive_subfolders(folder_id):
    query = "'%s' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false" % folder_id
    params = urllib.parse.urlencode({
        'q': query,
        'key': config.API_KEY,
        'fields': 'files(id,name)',
        'pageSize': 100,
    })
    url = '%s?%s' % (DRIVE_FILES_URL, params)
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, cafile=certifi.where()) as response:
        data = response.read()
    files = json.loads(data).get('files', [])
    return {f['name']: f['id'] for f in files if f.get('id') and f.get('name')}

@functools.lru_cache(maxsize=None)
def find_drive_file_id(folder_id, filename):
    escaped = filename.replace('\\', '\\\\').replace("'", "\\'")
    query = "'%s' in parents and name = '%s' and trashed = false" % (folder_id, escaped)
    params = urllib.parse.urlencode({
        'q': query,
        'key': config.API_KEY,
        'fields': 'files(id)',
        'pageSize': 1,
    })
    url = '%s?%s' % (DRIVE_FILES_URL, params)
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, cafile=certifi.where()) as response:
        data = response.read()
    files = json.loads(data).get('files', [])
    return files[0]['id'] if files else ''

def walk_drive_folder_path(root_id, segments):
    # Walks a list of subfolder names down from root_id, matching one level
    # per segment (e.g. ['gallery', 'album1']). Returns the final folder's
    # id, or '' if the root is unset or any segment along the way is missing.
    folder_id = root_id
    for segment in segments:
        if not folder_id:
            return ''
        try:
            subfolders = list_drive_subfolders(folder_id)
        except urllib.error.HTTPError:
            return ''
        folder_id = subfolders.get(segment, '')
    return folder_id

# Where downloaded Drive images are written, relative to the build output
# (config.BUILD_PATH). Written directly into the *build output*, not the
# tracked assets/ source folder — like the rest of docs/, it's regenerated
# every build and never committed.
MEMBER_IMAGE_CACHE_DIR = 'assets/images/members-drive-cache'

@functools.lru_cache(maxsize=None)
def download_drive_image(file_id, filename):
    # Downloads the file's bytes into the build output so a site visitor
    # loads it from this site's own CDN, instead of every page view hitting
    # Google Drive's slower thumbnail endpoint directly. Falls back to that
    # thumbnail URL if the download itself fails, so a Drive hiccup degrades
    # rather than breaks the image. Cached per (file_id, filename) so the
    # same photo referenced twice in one build downloads only once.
    ext = os.path.splitext(filename)[1] or '.jpg'
    dest_name = file_id + ext
    dest_dir = os.path.join(config.BUILD_PATH, *MEMBER_IMAGE_CACHE_DIR.split('/'))
    dest_path = os.path.join(dest_dir, dest_name)
    url_path = '/%s/%s' % (MEMBER_IMAGE_CACHE_DIR, dest_name)
    thumbnail_url = 'https://drive.google.com/thumbnail?id=%s&sz=w1600' % file_id

    download_url = '%s/%s?alt=media&key=%s' % (DRIVE_FILES_URL, file_id, config.API_KEY)
    req = urllib.request.Request(download_url)
    try:
        with urllib.request.urlopen(req, cafile=certifi.where()) as response:
            data = response.read()
    except Exception as e:
        # Any failure here (HTTP error, dropped connection, timeout, ...)
        # should degrade to the slower-but-working thumbnail URL rather than
        # fail the whole build.
        print('Warning: failed to download Drive file %s (%s); using the (slower) Drive thumbnail URL instead' % (file_id, e))
        return thumbnail_url

    os.makedirs(dest_dir, exist_ok=True)
    with open(dest_path, 'wb') as f:
        f.write(data)
    return url_path

def resolve_drive_image_path(root_id, path):
    # Resolves a Drive-relative path like 'member/pi/pic.jpg' (subfolder
    # names down to a filename) by walking subfolders from root_id, looking
    # up the file by exact name in the final folder, and downloading it into
    # the build output (see download_drive_image). Returns '' if the root is
    # unset or any segment isn't found.
    segments = [s for s in (path or '').strip().strip('/').split('/') if s]
    if not root_id or not segments:
        return ''
    *folder_names, filename = segments
    folder_id = walk_drive_folder_path(root_id, folder_names)
    if not folder_id:
        return ''
    try:
        file_id = find_drive_file_id(folder_id, filename)
    except urllib.error.HTTPError:
        return ''
    return download_drive_image(file_id, filename) if file_id else ''

def load_ranges(doc_id, ranges):
    if not config.API_KEY:
        raise RuntimeError('API_KEY is empty. Set the API_KEY secret (repo Settings -> Secrets and variables -> Actions).')
    if not doc_id:
        raise RuntimeError('DATA_URL is empty or has no document id. Set the DATA_URL secret to your Google Sheets URL.')
    params = '&'.join(['ranges=%s' % urllib.parse.quote(r) for r in ranges])
    url = '%s/%s/values:batchGet?%s&key=%s' % (SHEETS_URL_BASE, doc_id, params, config.API_KEY)

    req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req, cafile=certifi.where()) as response:
            data = response.read()
    except urllib.error.HTTPError as e:
        # urllib hides the response body; print Google's actual error reason
        # (e.g. API_KEY_HTTP_REFERRER_BLOCKED, SERVICE_DISABLED, API_KEY_INVALID).
        body = e.read().decode('utf-8', 'replace')
        print('Google Sheets API returned HTTP %s. Response body:\n%s' % (e.code, body))
        raise
    data_dict = json.loads(data)
    # A range with no data omits the 'values' key, so default to an empty list.
    return [r.get('values', []) for r in data_dict['valueRanges']]

def row_to_dict(row, keys, start_at=0):
    i = start_at
    result_dict = {}
    for key in keys:
        if len(row) > i:
            result_dict[key] = row[i]
        else:
            result_dict[key] = ''
        i += 1
    return result_dict

def is_empty_row(row):
    # Google Sheets omits trailing empty cells, so a row may be short or empty.
    # Treat a row with no value in its first column as a blank/junk row.
    return not row or not str(row[0]).strip()

def conv_website(table):
    items = {}
    for row in table:
        if is_empty_row(row):
            continue
        items[row[0]] = row[1] if len(row) > 1 else ''
    return items

def conv_announcements(table):
    items = []
    for row in table:
        if is_empty_row(row):
            continue
        if len(row) > 2 and row[2]:
            expire_at = dateutil.parser.parse(row[2])
            now = datetime.now(timezone.utc)
            if expire_at <= now:
                # This is already expired.
                continue
        items.append({
            'title': row[0],
            'content': row[1] if len(row) > 1 else ''
        })
    return items

# Top-level Drive subfolders (inside the shared root) that resolve_drive_image
# will follow. A path is only sent through Drive resolution when its first
# segment is one of these; anything else (a full URL, a repo asset path like
# "/assets/...") is left untouched, so plain URLs keep working everywhere.
DRIVE_IMAGE_FOLDERS = {'member'}

def resolve_drive_image(image, root_id):
    # A path like "/member/pi/pic.jpg" is resolved against the Drive root
    # folder; see DRIVE_IMAGE_FOLDERS.
    image = (image or '').strip()
    segments = image.strip('/').split('/')
    if not image or not root_id or segments[0].lower() not in DRIVE_IMAGE_FOLDERS:
        return image
    resolved = resolve_drive_image_path(root_id, image)
    if not resolved:
        print('Warning: image path "%s" not found in Drive root folder' % image)
        return image
    return resolved

# Research topic images live in the repo instead of Drive (faster, and not
# subject to Drive's thumbnail cropping/aspect ratio).
RESEARCH_IMAGE_DIR = '/assets/images/researches/'

def resolve_research_image(image):
    # A bare filename (e.g. "dialsm.jpg") is resolved to
    # assets/images/researches/ in this repo. A full URL or an absolute path
    # (e.g. "/assets/images/research-example.svg") is used as-is; a path
    # already rooted at "assets/" just gets its leading slash added back.
    image = (image or '').strip()
    if not image:
        return image
    if image.startswith('assets/'):
        return '/' + image
    if image.startswith('/') or re.match(r'^[a-zA-Z][a-zA-Z0-9+.-]*://', image):
        return image
    return RESEARCH_IMAGE_DIR + image

def conv_members(table, root_id=''):
    groups = []
    group = None
    for row in table:
        if is_empty_row(row):
            continue
        title = row[0]
        if group is None or group['title'] != title:
            if group:
                groups.append(group)
            group = {'title': title, 'members': []}
        member = row_to_dict(row, ['name', 'email', 'image', 'description', 'links', 'degree', 'year'], 1)
        member['image'] = resolve_drive_image(member.get('image', ''), root_id)
        group['members'].append(member)
    if group:
        groups.append(group)
    return groups

# Simple [tag]text[/tag] shortcuts so a sheet editor doesn't have to remember
# raw HTML/CSS for common inline formatting. Each expands to a plain HTML
# tag, which both the noscript (Python-Markdown) and interactive
# (markdown-it, via <vue-markdown :html="true">) renderers pass through as-is.
TEXT_SHORTCUTS = [
    (re.compile(r'\[red\](.*?)\[/red\]', re.I | re.S), r'<span style="color:#c0392b">\1</span>'),
    (re.compile(r'\[blue\](.*?)\[/blue\]', re.I | re.S), r'<span style="color:#2563eb">\1</span>'),
    (re.compile(r'\[b\](.*?)\[/b\]', re.I | re.S), r'<strong>\1</strong>'),
    (re.compile(r'\[i\](.*?)\[/i\]', re.I | re.S), r'<em>\1</em>'),
    (re.compile(r'\[u\](.*?)\[/u\]', re.I | re.S), r'<u>\1</u>'),
]

def apply_text_shortcuts(text):
    text = text or ''
    for pattern, replacement in TEXT_SHORTCUTS:
        text = pattern.sub(replacement, text)
    return text

def conv_research(table):
    groups = []
    group = None
    for row in table:
        if is_empty_row(row):
            continue
        title = row[0]
        if group is None or group['title'] != title:
            if group:
                groups.append(group)
            group = {'title': title, 'rows': []}
        item = row_to_dict(row, ['title', 'authors', 'booktitle', 'links', 'tags'], 1)
        if 'tags' in item:
            item['tags'] = [tag.strip() for tag in (item['tags'] or '').split(',') if tag]
        item['authors'] = apply_text_shortcuts(item.get('authors', ''))
        item['booktitle'] = apply_text_shortcuts(item.get('booktitle', ''))
        group['rows'].append(item)
    if group:
        groups.append(group)
    return groups

def conv_tags(table):
    # Row 2 (the tab's first data row) is reserved as an on/off switch for
    # the whole Topics feature (see topics_enabled) rather than a real tag,
    # so real tags start from row 3.
    tags = {}
    for row in table[1:]:
        if is_empty_row(row):
            continue
        tags[row[0]] = {
            'title': row[1] if len(row) > 1 else '',
            'tag': row[2] if len(row) > 2 else '',
            'color': row[3] if len(row) > 3 else '',
        }
    return tags

def topics_enabled(table):
    # Row 2's Tag (B) column is the switch: "off" hides the Topics filter
    # bar and per-paper tag badges everywhere on Publications. Anything else
    # (on, blank, or a missing row) leaves it on.
    switch_row = table[0] if table else []
    switch_value = (switch_row[1] if len(switch_row) > 1 else '').strip().lower()
    return switch_value != 'off'

def conv_links(table):
    groups = []
    group = None
    for row in table:
        if is_empty_row(row):
            continue
        title = row[0]
        if group is None or group['title'] != title:
            if group:
                groups.append(group)
            group = {'title': title, 'rows': []}
        item = row_to_dict(row, ['title', 'full_title', 'url', 'query', 'call_month', 'event_month'], 1)
        group['rows'].append(item)
    if group:
        groups.append(group)
    return groups

def conv_personal_website(table):
    items = {}
    for row in table:
        if not row or not row[0].strip():
            continue
        items[row[0]] = row[1] if len(row) > 1 else ''
    return items

def conv_personal_contents(table):
    contents = []
    for row in table:
        if len(row) < 2 or not row[0].strip():
            continue
        contents.append({'title': row[0], 'content': row[1]})
    return contents

def load_personal(table):
    websites = []
    for row in table:
        pathname = row[0].strip()
        url = row[1].strip()
        if not pathname or not url:
            continue
        websites.append({'path': pathname, 'url': url})
    
    websites_returned = list()
    for website in websites:
        data_url = website['url']
        doc_id = get_doc_id(data_url)
        try:
            tables = load_ranges(doc_id, PERSONAL_RANGES)
        except urllib.error.HTTPError:
            print("Error: {}".format(website))
            continue
        website['website'] = conv_personal_website(tables[0])
        website['contents'] = conv_personal_contents(tables[1])
        websites_returned.append(website)

    return websites_returned

def conv_pages(table):
    pages = []
    for row in table:
        if len(row) < 3 or not row[0].strip():
            continue
        pathname = row[0].strip()
        title = row[1].strip()
        content = row[2]
        if not pathname or not title or not content:
            continue
        pages.append({'path': pathname, 'title': title, 'content': content})
    return pages

def conv_redirects(table):
    redirects = []
    for row in table:
        if len(row) < 2 or not row[0].strip():
            continue
        pathname = row[0].strip()
        url = row[1].strip()
        if not pathname or not url:
            continue
        redirects.append({'path': pathname, 'url': url})
    return redirects

def conv_menu(table):
    # Group rows by the first column (top-level label), following the same
    # pattern as members/research/links. A row with an empty second column
    # sets the top-level item's own link; rows with a second column become
    # submenu items, which turns the top-level item into a dropdown.
    groups = []
    group = None
    for row in table:
        if is_empty_row(row):
            continue
        title = row[0].strip()
        sub = row[1].strip() if len(row) > 1 else ''
        url = row[2].strip() if len(row) > 2 else ''
        if group is None or group['title'] != title:
            if group:
                groups.append(group)
            group = {'title': title, 'url': '', 'children': []}
        if sub:
            group['children'].append({'title': sub, 'url': url})
        else:
            group['url'] = url
    if group:
        groups.append(group)
    return groups

def load_menu(doc_id):
    try:
        tables = load_ranges(doc_id, [MENU_RANGE])
    except urllib.error.HTTPError:
        # No 'Menu' tab in the spreadsheet yet.
        return DEFAULT_MENU
    menu = conv_menu(tables[0]) if tables else []
    return menu or DEFAULT_MENU

def slugify(text):
    text = (text or '').strip().lower()
    text = re.sub(r'[^a-z0-9]+', '-', text)
    return text.strip('-')

def get_sheet_titles(doc_id):
    url = '%s/%s?fields=sheets.properties.title&key=%s' % (SHEETS_URL_BASE, doc_id, config.API_KEY)
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, cafile=certifi.where()) as response:
        data = response.read()
    data_dict = json.loads(data)
    return [s['properties']['title'] for s in data_dict.get('sheets', [])]

def load_member_pages(doc_id, root_id=''):
    pages = []
    try:
        titles = get_sheet_titles(doc_id)
    except urllib.error.HTTPError:
        return pages
    for title in titles:
        if not title.startswith(MEMBER_PAGE_PREFIX):
            continue
        name = title[len(MEMBER_PAGE_PREFIX):].strip()
        # "Members - pi|Principal Investigator" splits the URL slug from the
        # displayed page title, so the URL can stay short while the page
        # shows a full name. Without a "|", the tab name is used for both,
        # same as before.
        if '|' in name:
            slug_source, display_name = name.split('|', 1)
            slug = slugify(slug_source)
            display_name = display_name.strip()
        else:
            slug = slugify(name)
            display_name = name
        if not display_name or not slug:
            continue
        try:
            tables = load_ranges(doc_id, ["'%s'!A2:H" % title])
        except urllib.error.HTTPError:
            print('Error: unable to load member page tab "%s"' % title)
            continue
        pages.append({
            'slug': slug,
            'title': display_name,
            'members': conv_members(tables[0], root_id) if tables else [],
        })
    return pages

def load_gallery(doc_id, root_id=''):
    try:
        tables = load_ranges(doc_id, [GALLERY_RANGE])
    except urllib.error.HTTPError:
        # No 'Gallery' tab in the spreadsheet yet.
        return []
    rows = tables[0] if tables else []

    # Album folders are named subfolders inside the root Drive folder
    # (Website tab 'root_folder'), so a row only needs the subfolder name
    # (or a "sub/folder" path, for a folder nested more than one level deep).
    subfolders = {}
    if root_id:
        try:
            subfolders = list_drive_subfolders(root_id)
        except urllib.error.HTTPError:
            print('Error: cannot list the gallery root folder')

    albums = []
    for row in rows:
        if not row:
            continue
        title = (row[0] if len(row) > 0 else '').strip()
        ref = (row[1] if len(row) > 1 else '').strip()
        # Skip only fully empty rows; an album may have just a title, just a
        # folder, or both.
        if not title and not ref:
            continue
        # Allow a literal "\n" typed in the cell to act as a line break, in
        # addition to real line breaks (Alt+Enter).
        content = (row[2] if len(row) > 2 else '').replace('\\n', '\n')
        # A full Drive link is used as-is; a "sub/folder" path is walked one
        # segment at a time from the root; otherwise treat the value as the
        # name of a direct subfolder of the root.
        stripped_ref = ref.strip('/')
        if '/folders/' in ref or 'drive.google' in ref:
            folder_id = get_drive_folder_id(ref)
        elif '/' in stripped_ref:
            folder_id = walk_drive_folder_path(root_id, stripped_ref.split('/'))
        else:
            folder_id = subfolders.get(ref, '')
        photos = []
        if folder_id:
            try:
                photos = list_drive_images(folder_id)
            except urllib.error.HTTPError:
                print('Error: cannot list Drive folder for gallery album "%s"' % title)
        elif ref:
            print('Warning: gallery album "%s": folder "%s" not found in root' % (title, ref))
        albums.append({'title': title, 'content': content, 'photos': photos})
    return albums

def conv_research_intro(table):
    # Research-introduction page: one row per topic (title, image, Markdown).
    items = []
    for row in table:
        if not row:
            continue
        title = (row[0] if len(row) > 0 else '').strip()
        image = (row[1] if len(row) > 1 else '').strip()
        content = (row[2] if len(row) > 2 else '').replace('\\n', '\n')
        if not title and not image and not content.strip():
            continue
        items.append({'title': title, 'image': resolve_research_image(image), 'content': content})
    return items

def load_publications(doc_id):
    try:
        tables = load_ranges(doc_id, [PUBLICATIONS_RANGE])
    except urllib.error.HTTPError:
        return []
    return conv_research(tables[0]) if tables else []

def load_research_intro(doc_id):
    try:
        tables = load_ranges(doc_id, [RESEARCH_RANGE])
    except urllib.error.HTTPError:
        return []
    return conv_research_intro(tables[0]) if tables else []

def load_data():
    data_url = config.DATA_URL
    doc_id = get_doc_id(data_url)
    tables = load_ranges(doc_id, RANGES)
    website = conv_website(tables[0])
    # 'root_folder' is the shared Drive root backing gallery albums and
    # member images (member/..., gallery/... subfolders inside it). Research
    # images live in the repo instead (see resolve_research_image).
    # 'gallery_folder' is the old key name, kept for sites that haven't
    # renamed it in their sheet yet.
    root_id = get_drive_folder_id(website.get('root_folder') or website.get('gallery_folder', ''))
    return {
        'website': website,
        'announcements': conv_announcements(tables[1]),
        'members': conv_members(tables[2], root_id),
        'tags': conv_tags(tables[3]),
        'topics_enabled': topics_enabled(tables[3]),
        'links': conv_links(tables[4]),
        'pages': conv_pages(tables[5]),
        'redirects': conv_redirects(tables[6]),
        'personal': load_personal(tables[7]),
        'publications': load_publications(doc_id),
        'research': load_research_intro(doc_id),
        'menu': load_menu(doc_id),
        'member_pages': load_member_pages(doc_id, root_id),
        'gallery': load_gallery(doc_id, root_id),
    }

