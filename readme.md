# Research Group Static Website

This is a static website for a research group, hosted as GitHub Pages.

The website rebuilds itself every 30 minutes from a Google Sheets document via a scheduled GitHub Actions job, so editing the spreadsheet is enough to update the site.

![Builder](https://github.com/TBDLAB1/tbdlab1.github.io/actions/workflows/builder.yml/badge.svg)

## How does this website work?

The [Builder workflow](.github/workflows/builder.yml) runs the Python builder in *[builder](builder)*, which downloads the contents from Google Sheets and renders the static site into the *docs* folder **on the runner**. It then deploys that folder straight to GitHub Pages as an artifact — **nothing is committed back to the repository.**

The workflow runs:
- every 30 minutes (scheduled),
- on every push to *master*, and
- manually via the **Run workflow** button on the [Actions](https://github.com/TBDLAB1/tbdlab1.github.io/actions/workflows/builder.yml) page.

> The *docs* folder is a build artifact — it is regenerated on every run and you do **not** need to commit it. To update the site, edit the Google Sheets document (or push a code change), then let the workflow run.

## How to upload static files to this website

If you need to upload images or any other static files for use on the website, put them in the *[assets](assets)* folder. Everything there is copied into the built site's *assets* folder at build time.

## How to create your own website from this

1. Fork this repository to your account.

1. Configure the repository to publish GitHub Pages using **GitHub Actions** as the source: *Settings → Pages → Build and deployment → Source → **GitHub Actions***. (This project deploys the built site as an artifact, so do **not** use "Deploy from a branch".)

1. Configure a custom domain for your website if you need to. Read [this document](https://docs.github.com/en/free-pro-team@latest/github/working-with-github-pages/configuring-a-custom-domain-for-your-github-pages-site) if you need help.

1. Create a Google Sheets document for your contents and add its URL as the `DATA_URL` secret (see below).

1. Get a Google API key and add it as the `API_KEY` secret (see below).

1. Voilà! Once the workflow runs, your website is live on GitHub Pages.

The spreadsheet URL and API key are read from the `DATA_URL` and `API_KEY` **repository secrets** (Settings → Secrets and variables → Actions), so they are never committed to the repo. For a local build, pass them as environment variables:

```bash
INPUT_API_KEY=<key> INPUT_DATA_URL=<sheet-url> python3 build.py
```

### Create a data source document

The site's contents come from a Google Sheets document, whose URL is stored in the `DATA_URL` secret.

An example document is available at [here](https://docs.google.com/spreadsheets/d/1EDLlUuY2Ia5MKNbCTOftxxSxBaK3C9pRFOIUvMY30eY/edit?usp=sharing).

To create your own document, follow the instructions below. 

1. Use [this link](https://docs.google.com/spreadsheets/d/1EDLlUuY2Ia5MKNbCTOftxxSxBaK3C9pRFOIUvMY30eY/copy#gid=1676718498) to make a copy of the example Sheets document. 

1. Set your document's sharing settings as: *Public on the web - Anyone on the Internet can find and view*. Read [this document](https://support.google.com/docs/answer/183965?co=GENIE.Platform%3DDesktop&hl=en) if you need help.

1. Add the document URL as the `DATA_URL` secret (Settings → Secrets and variables → Actions → New repository secret).

### Get a Google API Key

The builder needs a Google API key to read the Google Sheets document. Add it as the `API_KEY` secret.

1. Create an API key in the [Google Cloud Console](https://console.cloud.google.com/apis/credentials) and enable the **Google Sheets API** for its project.
1. Set **Application restrictions → None** (no HTTP referrer restriction). The builder calls the API server-side with no referrer, so a referrer-restricted key fails with `403`.
1. Add the key as the `API_KEY` secret.

## Configuring the navigation menu

The top navigation bar is driven by a **`Menu`** tab in the Google Sheets document (columns `Menu`, `Submenu`, `URL`, with data starting at row 2). Each row is one entry:

| Menu | Submenu | URL |
| --- | --- | --- |
| Home | | / |
| Members | PI | /members/pi |
| Members | Students | /members/students |
| Research | | /research |
| Contact | | /contact |

- Leave **Submenu** empty for a normal, one-level link (e.g. *Home*, *Research*).
- Fill **Submenu** to turn that **Menu** label into a two-level dropdown; every row sharing the same **Menu** value becomes an item in that dropdown (e.g. *Members → PI / Students*).

If there is no `Menu` tab, the site falls back to the default menu (Home, Members, Research, Links, Contact).

## Creating separate member pages

In addition to the combined */members* page (built from the `Members` tab), you can publish extra member pages, each managed in its own tab:

1. Add a tab named **`Members - <Name>`** (e.g. `Members - PI`, `Members - Students`) using the **same columns as the `Members` tab**.
1. It is automatically published at **`/members/<name>`**, where `<name>` is lower-cased with spaces turned into hyphens (`Members - PI` → `/members/pi`).
1. Link to it from the `Menu` tab (see above).

Within each page, column A is still the section heading, so a single page can hold several groups (e.g. a *Students* page with *Ph.D. Student*, *M.S. Student*, … sections).

## Gallery & member photos (from one Google Drive folder)

Both the `/gallery` page and member photos (the `image` column on the `Members` / `Members - <Name>` tabs) can pull images straight from **one shared Google Drive folder**, instead of pasting a link per photo.

**Setup:**

1. Make a Drive folder, share it *Anyone with the link – Viewer*, and inside it create top-level subfolders as needed, e.g.:

    ```
    root/
      member/
        pi/pic.jpg
        alice/pic.jpg
      gallery/
        album1/  (photos for this album)
        album2/
    ```

2. In the **`Website`** tab, add a `root_folder` key whose value is the **root folder's share link**. (This one root now backs both the gallery and member photos. The old key name `gallery_folder` still works, for sites that haven't renamed it yet.)
3. **Member photo:** in the `image` column, write the path from the root folder, starting with `member/` (e.g. `member/pi/pic.jpg`). It's resolved to a Drive thumbnail at build time.
4. **Gallery album:** in a **`Gallery`** tab (from row 2), add one row per album:

    | Title | Folder | Description (Markdown) |
    | --- | --- | --- |
    | Jeju Conference | gallery/album1 | ## We had a great time … |
    | Workshop | gallery/album2 | |

    - **Title** (A) is what's shown on the page; **Folder** (B) is the path from the root folder to the album's subfolder (a bare name like `album1` also works if it's a *direct* child of the root); **Description** (C) is optional Markdown. For line breaks in the description, press **Alt+Enter** in the cell (typing a literal `\n` also works).
    - Every image in that subfolder becomes a slide (ordered by file name). Album order and titles are controlled by the sheet.
    - Add an album = add a subfolder + a sheet row; add photos = drop files into the subfolder.
    - (You can also put a full Drive folder link in column B instead of a path.)

Anything that doesn't start with `member/` (a full URL, a repo asset path like `/assets/...`) is left as-is, so existing member photos keep working unchanged.

**Requirements:** the `API_KEY` must have the **Google Drive API** enabled (in addition to Sheets), the folders must be publicly viewable, and the page is linked from the `Menu` tab (`Gallery → /gallery`).

## Research & Publications

- **Publications** (`/publications`) is the paper list — built from a **`Publications`** tab (same layout the old `Research` tab used: `Category`, `Title`, `Authors`, `Booktitle`, `Links`, `Tags`).
- **Research** (`/research`) is an introduction page — built from a **`Research`** tab with one row per topic:

| Title | Image | Content (Markdown) |
| --- | --- | --- |
| Natural Language Processing | /assets/images/research-example.svg | We study … |

Each row renders as a **title + one image (16:10) + Markdown description**, repeated down the page. The image is any URL or path (a repo asset, a Drive `thumbnail?id=…` link, etc.); a sample 16:10 image lives at `/assets/images/research-example.svg`. Link both pages from the `Menu` tab.

## Acknowledgements

This work was supported and funded by [JinYeong Bak](https://nosyu.github.io/). The developer of this repo is [Jeongmin Byun](https://jmbyun.github.io/).

## Tips
- How to do line breaks in markdown
  - Two spaces at the end of the line (recommended, https://stackoverflow.com/a/33191810)
  - One empty line between lines
  - Reference: https://gist.github.com/shaunlebron/746476e6e7a4d698b373
- How to update the webpage
  - Edit the Google Sheets document (contents) or the *assets* folder (static files), then wait up to 30 minutes, **or**
  - Go to the [Actions](https://github.com/TBDLAB1/tbdlab1.github.io/actions/workflows/builder.yml) page and click the `Run workflow` button to update immediately
