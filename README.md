# PDF Renamer

A macOS desktop app that automatically renames PDF files using the title found inside each file — either from the PDF's built-in metadata or from the largest text on the first page.

Designed by **Soheil Jamali** & AI.

---

## What it does

Most PDFs downloaded from the internet have meaningless file names like `document_v2_final.pdf` or `1234567.pdf`. PDF Renamer opens each file, reads its actual title, and renames the file to match — all without you having to open a single PDF manually.

---

## Features

- **Auto title detection** — reads the PDF's metadata title first, then falls back to the largest text on the first page
- **Preview before renaming** — see every old name → new name mapping in a table before anything is changed
- **Click to ignore** — click any row to exclude that file from renaming; click again to include it
- **Inline name editing** — double-click the "New name" cell to type a custom name
- **Select All / Deselect All** — toggle all files at once
- **Search / filter** — type in the filter box to instantly narrow the list by file name
- **Sort columns** — click any column heading to sort ascending or descending
- **Progress bar** — shows scan progress on large folders
- **Undo rename** — reverse all renames and restore original file names after the fact
- **Conflict auto-resolve** — if a new name already exists, automatically appends (2), (3), etc.
- **Recursive scan** — optionally include PDFs inside subfolders
- **Export CSV** — save a spreadsheet of the old → new name mappings
- **Drag & drop** — drag a folder from Finder onto the window to scan it
- **Remembers last folder** — reopens the same folder on next launch
- **Dark mode** — checkbox in the title bar to switch between light and dark themes; auto-detects your macOS system appearance on launch
- **Open PDF** — right-click any row to open the PDF in your default viewer

---

## Source types

The "Source" column in the table tells you how the new name was determined:

| Source | Meaning |
|---|---|
| `metadata` | Title was found inside the PDF's built-in file properties |
| `page text` | Title was read from the largest text on the first page |
| *(blank)* | No title could be found — file will be skipped |

---

## Requirements

- macOS
- Python 3.10 or later
- The following Python packages:

```
pypdf
pdfplumber
tkinterdnd2
```

Install them with:

```bash
pip3 install pypdf pdfplumber tkinterdnd2
```

---

## How to run

```bash
python3 rename_pdfs.py
```

---

## How to use

1. Launch the app with `python3 rename_pdfs.py`
2. Click **Choose Folder & Scan** (or drag a folder onto the window)
3. Review the table — green rows will be renamed, gray rows are skipped
4. Click any row to ignore it; double-click the "New name" cell to edit it manually
5. Click **Rename Selected** when you are ready
6. Use **Undo Rename** if you want to reverse the changes

> **Tip:** If the app is not responding to clicks right after launch, try moving the window slightly — this is a known macOS focus quirk and moving the window fixes it immediately.

---

## Project structure

```
rename_pdfs.py   — the entire app (single file)
```

---

## License

This project is for personal use. Feel free to modify it for your own needs.
