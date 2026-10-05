#!/usr/bin/env python3
"""
PDF Renamer
-----------
Scans a folder for PDF files and renames each one using:
  1. The PDF's metadata title (if set)
  2. Otherwise, the first prominent text found on the first page
If neither is found, the file is left unchanged.
"""

import csv
import json
import logging
import os
import re
import subprocess
import warnings
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path

_CONFIG_PATH = Path.home() / '.pdf_renamer_config.json'


def _load_config() -> dict:
    try:
        return json.loads(_CONFIG_PATH.read_text())
    except Exception:
        return {}


def _save_config(data: dict) -> None:
    try:
        _CONFIG_PATH.write_text(json.dumps(data))
    except Exception:
        pass

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD  # type: ignore[import-untyped]
    _DND_AVAILABLE = True
except ImportError:
    DND_FILES = None  # type: ignore[assignment]
    TkinterDnD = None  # type: ignore[assignment]
    _DND_AVAILABLE = False


def _is_dark_mode() -> bool:
    try:
        result = subprocess.run(
            ['defaults', 'read', '-g', 'AppleInterfaceStyle'],
            capture_output=True, text=True, timeout=2)
        return result.stdout.strip().lower() == 'dark'
    except Exception:
        return False


_LIGHT = {
    'bg': '#f5f5f7', 'fg': '#111111', 'fg_dim': '#555555', 'fg_muted': '#888888',
    'tree_bg': '#ffffff', 'tree_fg': '#111111', 'heading_bg': '#e0e0e0',
    'entry_border': '#cccccc', 'filter_bg': '#ffffff',
    'bottom_fg': '#222222',
}
_DARK = {
    'bg': '#1c1c1e', 'fg': '#f0f0f0', 'fg_dim': '#aaaaaa', 'fg_muted': '#777777',
    'tree_bg': '#2c2c2e', 'tree_fg': '#f0f0f0', 'heading_bg': '#3a3a3c',
    'entry_border': '#555555', 'filter_bg': '#3a3a3c',
    'bottom_fg': '#ffffff',
}

import pypdf
import pdfplumber

logging.getLogger('pypdf').setLevel(logging.ERROR)
warnings.filterwarnings('ignore', module='pypdf')


def sanitize_filename(name: str) -> str:
    name = name.strip()
    name = re.sub(r'[\r\n\t]+', ' ', name)
    name = re.sub(r'[/\\:*?"<>|]', '', name)
    name = re.sub(r' {2,}', ' ', name)
    return name[:200].strip()


def get_metadata_title(pdf_path: str) -> "str | None":
    try:
        reader = pypdf.PdfReader(pdf_path)
        meta = reader.metadata
        if meta and meta.title and meta.title.strip():
            return meta.title.strip()
    except Exception:
        pass
    return None


_URL_RE = re.compile(
    r'^(https?://|www\.|ftp://|mailto:)|'
    r'^\S+\.(com|org|edu|net|gov|io|pdf|html?|php|aspx?)(/\S*)?$',
    re.IGNORECASE,
)


def _looks_like_url(text: str) -> bool:
    stripped = text.strip()
    if _URL_RE.search(stripped):
        return True
    if '.' in stripped and ' ' not in stripped and len(stripped) < 80:
        parts = stripped.split('.')
        if all(p.replace('-', '').replace('_', '').isalnum() for p in parts if p):
            return True
    return False


def get_first_page_title(pdf_path: str) -> "str | None":
    try:
        with pdfplumber.open(pdf_path) as pdf:
            if not pdf.pages:
                return None
            page = pdf.pages[0]
            words = page.extract_words(keep_blank_chars=False, extra_attrs=['size'])
            if words:
                lines: dict[float, list] = {}
                for w in words:
                    top = round(float(w.get('top', 0)), 0)
                    lines.setdefault(top, []).append(w)
                best_text: "str | None" = None
                best_score = -1.0
                for line_words in lines.values():
                    sizes = [float(w.get('size', 0) or 0) for w in line_words]
                    avg_size = sum(sizes) / len(sizes) if sizes else 0
                    text = ' '.join(w['text'] for w in line_words).strip()
                    if len(text) < 4 or _looks_like_url(text):
                        continue
                    if re.fullmatch(r'[\d\s\-–—/]+', text):
                        continue
                    if avg_size > best_score:
                        best_score = avg_size
                        best_text = text
                if best_text:
                    return best_text
            text = page.extract_text() or ''
            for line in text.splitlines():
                line = line.strip()
                if len(line) < 4 or _looks_like_url(line):
                    continue
                if re.fullmatch(r'[\d\s\-–—/]+', line):
                    continue
                return line
    except Exception:
        pass
    return None


def find_title(pdf_path: str) -> "tuple[str | None, str]":
    title = get_metadata_title(pdf_path)
    if title:
        return title, 'metadata'
    title = get_first_page_title(pdf_path)
    if title:
        return title, 'first_page'
    return None, 'none'


def resolve_conflict(new_path: Path, old_path: Path) -> Path:
    """Return new_path with (2), (3), … appended until no conflict exists."""
    if not new_path.exists() or new_path == old_path:
        return new_path
    stem = new_path.stem
    parent = new_path.parent
    counter = 2
    while True:
        candidate = parent / f"{stem} ({counter}).pdf"
        if not candidate.exists():
            return candidate
        counter += 1


def iter_renames(folder: str, recursive: bool = False):
    """Yield one result dict per PDF, allowing the caller to update a progress bar."""
    root = Path(folder)
    paths = sorted(root.rglob('*.pdf') if recursive else
                   (p for p in root.iterdir() if p.suffix.lower() == '.pdf'))
    for path in paths:
        title, source = find_title(str(path))
        if title:
            safe = sanitize_filename(title)
            new_name = safe + '.pdf'
            new_path = resolve_conflict(path.parent / new_name, path)
            new_name = new_path.name
            yield {
                'old_path': path,
                'new_name': new_name,
                'new_path': new_path,
                'source': source,
                'conflict': False,
                'same': new_name == path.name,
            }
        else:
            yield {
                'old_path': path,
                'new_name': None,
                'new_path': None,
                'source': 'none',
                'conflict': False,
                'same': False,
            }


# ── GUI ──────────────────────────────────────────────────────────────────────

_BaseClass = TkinterDnD.Tk if _DND_AVAILABLE else tk.Tk  # type: ignore[union-attr]


class App(_BaseClass):  # type: ignore[misc, valid-type]
    def __init__(self):
        super().__init__()
        self.title('PDF Renamer')
        self.geometry('1280x620')
        self.minsize(1280, 500)
        self.resizable(True, True)
        self._theme = _DARK if _is_dark_mode() else _LIGHT
        self.configure(bg=self._theme['bg'])

        cfg = _load_config()
        self._folder      = tk.StringVar(value=cfg.get('last_folder', ''))
        self._results:    list[dict] = []
        self._renameable: list[int]  = []
        self._ignored:    set[int]   = set()
        self._entry:      tk.Entry | None = None
        self._entry_idx:  int = -1
        self._undo_log:   list[tuple] = []
        self._recursive:  tk.BooleanVar = tk.BooleanVar(value=False)
        self._row_cache:    dict[int, tuple] = {}  # idx -> (old_name, new_text, source, tag)
        self._display_order: list[int] = []       # idx values in current sort order
        self._filter_var:   tk.StringVar = tk.StringVar()
        self._sort_col:     str = ''
        self._sort_asc:     bool = True
        self._dark_var:     tk.BooleanVar = tk.BooleanVar(value=(self._theme is _DARK))

        self._build_ui()

    # ── build ────────────────────────────────────────────────────────────────

    def _build_ui(self):
        t = self._theme
        style = ttk.Style()
        style.theme_use('default')
        style.configure('Treeview',
                        background=t['tree_bg'], foreground=t['tree_fg'],
                        fieldbackground=t['tree_bg'],
                        font=('SF Pro Text', 12), rowheight=36)
        style.configure('Treeview.Heading',
                        background=t['heading_bg'], foreground=t['fg'],
                        font=('SF Pro Text', 12, 'bold'))
        style.map('Treeview', background=[('selected', '#0051d4')],
                  foreground=[('selected', 'white')])

        top = tk.Frame(self, bg=t['bg'])
        top.pack(fill='x', padx=12, pady=6)

        tk.Label(top, text='PDF Renamer', font=('SF Pro Display', 18, 'bold'),
                 bg=t['bg'], fg=t['fg']).pack(side='left')

        tk.Checkbutton(top, text='Dark Mode',
                       variable=self._dark_var,
                       command=self._toggle_theme,
                       bg=t['bg'], fg=t['fg_dim'],
                       activebackground=t['bg'], activeforeground=t['fg'],
                       selectcolor=t['tree_bg'],
                       font=('SF Pro Text', 11),
                       cursor='arrow').pack(side='left', padx=(16, 0))

        btn_frame = tk.Frame(top, bg=t['bg'])
        btn_frame.pack(side='right')

        self._scan_btn = tk.Button(btn_frame, text='Choose Folder & Scan',
                                   command=self._choose_and_scan,
                                   bg='#007aff', fg='black',
                                   activebackground='#0051d4', activeforeground='black',
                                   highlightbackground='#007aff', highlightthickness=2,
                                   font=('SF Pro Text', 12),
                                   relief='flat', padx=12, pady=6, cursor='arrow')
        self._scan_btn.pack(side='left', padx=4)

        tk.Checkbutton(btn_frame, text='Include subfolders',
                       variable=self._recursive,
                       bg=t['bg'], fg=t['fg'],
                       activebackground=t['bg'], activeforeground=t['fg'],
                       selectcolor=t['tree_bg'],
                       font=('SF Pro Text', 11),
                       cursor='arrow').pack(side='left', padx=(8, 4))

        self._rename_btn = tk.Button(btn_frame, text='Rename Selected',
                                     command=self._do_rename,
                                     bg='#007aff', fg='black',
                                     activebackground='#0051d4', activeforeground='black',
                                     disabledforeground='black',
                                     highlightbackground='#007aff', highlightthickness=2,
                                     font=('SF Pro Text', 12),
                                     relief='flat', padx=12, pady=6,
                                     cursor='arrow', state='disabled')
        self._rename_btn.pack(side='left', padx=4)

        self._toggle_btn = tk.Button(btn_frame, text='Deselect All',
                                     command=self._toggle_all,
                                     bg='#007aff', fg='black',
                                     activebackground='#0051d4', activeforeground='black',
                                     disabledforeground='black',
                                     highlightbackground='#007aff', highlightthickness=2,
                                     font=('SF Pro Text', 12),
                                     relief='flat', padx=12, pady=6,
                                     cursor='arrow', state='disabled')
        self._toggle_btn.pack(side='left', padx=4)

        self._undo_btn = tk.Button(btn_frame, text='Undo Rename',
                                   command=self._do_undo,
                                   bg='#ff9500', fg='black',
                                   activebackground='#cc7700', activeforeground='black',
                                   highlightbackground='#ff9500', highlightthickness=2,
                                   font=('SF Pro Text', 12),
                                   relief='flat', padx=12, pady=6,
                                   cursor='arrow', state='disabled')
        self._undo_btn.pack(side='left', padx=4)

        self._csv_btn = tk.Button(btn_frame, text='Export CSV',
                                  command=self._export_csv,
                                  bg='#34c759', fg='black',
                                  activebackground='#248a3d', activeforeground='black',
                                  disabledforeground='black',
                                  highlightbackground='#34c759', highlightthickness=2,
                                  font=('SF Pro Text', 12),
                                  relief='flat', padx=12, pady=6,
                                  cursor='arrow', state='disabled')
        self._csv_btn.pack(side='left', padx=4)

        self._folder_lbl = tk.Label(self, textvariable=self._folder,
                                    font=('SF Pro Text', 11), fg=t['fg_dim'],
                                    bg=t['bg'], anchor='w')
        self._folder_lbl.pack(fill='x', padx=12)

        filter_frame = tk.Frame(self, bg=t['bg'])
        filter_frame.pack(fill='x', padx=12, pady=(4, 2))
        tk.Label(filter_frame, text='Filter:', font=('SF Pro Text', 11),
                 bg=t['bg'], fg=t['fg_dim']).pack(side='left')
        filter_entry = tk.Entry(filter_frame, textvariable=self._filter_var,
                                font=('SF Pro Text', 11), relief='flat',
                                bg=t['filter_bg'], fg=t['fg'],
                                insertbackground=t['fg'],
                                highlightthickness=1, highlightbackground=t['entry_border'],
                                highlightcolor='#007aff')
        filter_entry.pack(side='left', fill='x', expand=True, padx=(6, 0), ipady=4)
        self._filter_var.trace_add('write', lambda *_: self._apply_filter())

        table_frame = tk.Frame(self, bg=t['bg'])
        table_frame.pack(fill='both', expand=True, padx=12, pady=(0, 4))

        cols = ('Current name', 'New name', 'Source')
        self._tree = ttk.Treeview(table_frame, columns=cols, show='headings',
                                  selectmode='none')
        for col in cols:
            self._tree.heading(col, text=col,
                               command=lambda c=col: self._sort_by(c))
        self._tree.column('Current name', width=300, minwidth=120, stretch=True)
        self._tree.column('New name',     width=380, minwidth=120, stretch=True)
        self._tree.column('Source',       width=90,  minwidth=90,  stretch=False, anchor='center')

        vsb = ttk.Scrollbar(table_frame, orient='vertical', command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)

        vsb.pack(side='right', fill='y')
        self._tree.pack(side='left', fill='both', expand=True)

        self._tree.bind('<ButtonRelease-1>', self._on_row_click)
        self._tree.bind('<Double-ButtonRelease-1>', self._on_row_double_click)
        self._tree.bind('<Button-2>', self._on_row_right_click)
        self._tree.bind('<Button-3>', self._on_row_right_click)

        self._context_menu = tk.Menu(self, tearoff=0)
        self._context_menu.add_command(label='Open PDF', command=self._open_selected_pdf)
        self._context_row_id: str = ''

        self._progress = ttk.Progressbar(self, orient='horizontal', mode='determinate')

        self._status = tk.StringVar(value='Choose a folder to get started.')
        tk.Label(self, textvariable=self._status, font=('SF Pro Text', 13),
                 fg=t['bottom_fg'], bg=t['bg'], anchor='w').pack(
            fill='x', padx=12, pady=(0, 2))

        legend = (
            'Source types:  '
            'metadata = the title was found inside the PDF file\'s own properties  ·  '
            'page text = the title was read from the largest text on the first page  ·  '
            'none = no title could be found, so the file will be skipped\n'
            'Tip: if the app is not responding to clicks, try moving the window slightly — that usually fixes it.\n'
            'Designed by Soheil Jamali & AI'
        )
        tk.Label(self, text=legend, font=('SF Pro Text', 12),
                 fg=t['bottom_fg'], bg=t['bg'], anchor='w', wraplength=1200,
                 justify='left').pack(fill='x', padx=12, pady=(0, 8))

        if _DND_AVAILABLE:
            self.drop_target_register(DND_FILES)
            self.dnd_bind('<<Drop>>', self._on_drop)

    # ── activation ───────────────────────────────────────────────────────────

    def activate(self):
        self.lift()
        self.focus_force()
        self.attributes('-topmost', True)
        self.after(300, lambda: self.attributes('-topmost', False))

    # ── theme toggle ─────────────────────────────────────────────────────────

    def _toggle_theme(self):
        self._theme = _DARK if self._dark_var.get() else _LIGHT
        # Destroy all widgets and rebuild with new theme
        for widget in self.winfo_children():
            widget.destroy()
        self._build_ui()
        # Restore table if a scan was already done
        if self._results:
            self._repopulate_after_theme()

    def _repopulate_after_theme(self):
        """Re-insert cached rows without re-scanning."""
        for row in self._tree.get_children():
            self._tree.delete(row)
        for idx in self._display_order:
            old_name, new_text, source, base_tag = self._row_cache[idx]
            tag = 'ignored' if idx in self._ignored else base_tag
            self._tree.insert('', 'end', iid=str(idx),
                              values=(old_name, new_text, source),
                              tags=(tag,))
        self._configure_tags()
        self._update_status()

    # ── drag-and-drop ─────────────────────────────────────────────────────────

    def _on_drop(self, event: tk.Event):
        # tkinterdnd2 gives paths space-separated, wrapped in {} if they contain spaces
        raw = event.data.strip()  # type: ignore[attr-defined]
        # parse out the first path (handles braces for paths with spaces)
        if raw.startswith('{'):
            path = raw[1:raw.index('}')]
        else:
            path = raw.split()[0]
        p = Path(path)
        folder = str(p) if p.is_dir() else str(p.parent)
        self._folder.set(folder)
        self._scan_from(folder)

    # ── row click: toggle ignored ─────────────────────────────────────────────

    def _on_row_click(self, event: tk.Event):
        row_id = self._tree.identify_row(event.y)
        if not row_id:
            return
        idx = int(row_id)
        if idx not in self._renameable:
            return
        if idx in self._ignored:
            self._ignored.discard(idx)
            self._tree.item(row_id, tags=('rename',))
        else:
            self._ignored.add(idx)
            self._tree.item(row_id, tags=('ignored',))
        self._update_status()

    # ── inline editor ─────────────────────────────────────────────────────────

    def _on_row_right_click(self, event: tk.Event):
        row_id = self._tree.identify_row(event.y)
        if not row_id:
            return
        self._context_row_id = row_id
        self._context_menu.tk_popup(event.x_root, event.y_root)

    def _open_selected_pdf(self):
        if not self._context_row_id:
            return
        idx = int(self._context_row_id)
        if idx >= len(self._results):
            return
        path = self._results[idx]['old_path']
        subprocess.Popen(['open', str(path)])

    def _on_row_double_click(self, event: tk.Event):
        self._close_editor(save=False)
        row_id = self._tree.identify_row(event.y)
        col    = self._tree.identify_column(event.x)
        if not row_id or col != '#2':
            return
        idx = int(row_id)
        if idx not in self._renameable:
            return
        bbox = self._tree.bbox(row_id, col)
        if not bbox:
            return
        x, y, w, h = bbox
        current_val = self._tree.item(row_id, 'values')[1]

        self._entry_idx = idx
        self._entry = tk.Entry(self._tree, font=('SF Pro Text', 12),
                               relief='flat', bd=0,
                               highlightthickness=2,
                               highlightbackground='#007aff',
                               highlightcolor='#007aff')
        self._entry.insert(0, current_val)
        self._entry.select_range(0, 'end')
        self._entry.place(x=x, y=y, width=w, height=h)
        self._entry.focus_set()
        self._entry.bind('<Return>',   lambda _: self._close_editor(save=True))
        self._entry.bind('<Escape>',   lambda _: self._close_editor(save=False))
        self._entry.bind('<FocusOut>', lambda _: self._close_editor(save=True))

    def _close_editor(self, save: bool):
        if self._entry is None:
            return
        idx = self._entry_idx
        if save and idx >= 0:
            raw = self._entry.get().strip()
            if raw:
                if not raw.lower().endswith('.pdf'):
                    raw += '.pdf'
                base_name = sanitize_filename(raw[:-4]) + '.pdf'
                old_path  = self._results[idx]['old_path']
                new_path  = resolve_conflict(old_path.parent / base_name, old_path)
                new_name  = new_path.name
                self._results[idx].update(
                    new_name=new_name, new_path=new_path, conflict=False)
                vals  = list(self._tree.item(str(idx), 'values'))
                vals[1] = new_name
                tag = 'ignored' if idx in self._ignored else 'rename'
                self._tree.item(str(idx), values=vals, tags=(tag,))
                self._row_cache[idx] = (vals[0], new_name, vals[2], tag)
        self._entry.destroy()
        self._entry = None
        self._entry_idx = -1

    # ── scan / populate ───────────────────────────────────────────────────────

    def _choose_and_scan(self):
        self.lift()
        self.focus_force()
        self.attributes('-topmost', True)
        folder = filedialog.askdirectory(title='Select folder with PDF files', parent=self)
        self.attributes('-topmost', False)
        if not folder:
            return
        self._folder.set(folder)
        self._scan_from(folder)

    def _scan_from(self, folder: str):
        _save_config({'last_folder': folder})
        recursive = self._recursive.get()
        root = Path(folder)
        pdf_paths = (sorted(root.rglob('*.pdf')) if recursive
                     else sorted(p for p in root.iterdir() if p.suffix.lower() == '.pdf'))
        total = len(pdf_paths)

        self._progress.config(maximum=max(total, 1), value=0)
        self._progress.pack(fill='x', padx=12, pady=(0, 4))
        self._status.set(f'Scanning 0 / {total}…')
        self.update()

        self._results = []
        for i, result in enumerate(iter_renames(folder, recursive=recursive), start=1):
            self._results.append(result)
            self._progress['value'] = i
            self._status.set(f'Scanning {i} / {total}…')
            self.update()

        self._progress.pack_forget()
        self._populate_table()

    def _populate_table(self):
        self._close_editor(save=False)
        for row in self._tree.get_children():
            self._tree.delete(row)
        self._ignored.clear()
        self._renameable.clear()
        self._row_cache.clear()
        self._display_order.clear()
        self._sort_col = ''
        self._sort_asc = True
        self._filter_var.set('')

        for idx, r in enumerate(self._results):
            old_name = r['old_path'].name
            if r['new_name'] is None:
                new_text, tag = '— no title found —', 'skip'
            elif r['same']:
                new_text, tag = '(already correct)', 'same'
            elif r['conflict']:
                new_text = r['new_name'] + '  ⚠ name taken'
                tag = 'conflict'
            else:
                new_text, tag = r['new_name'], 'rename'
                self._renameable.append(idx)

            source = {'metadata': 'metadata', 'first_page': 'page text',
                      'none': ''}.get(r['source'], '')
            self._row_cache[idx] = (old_name, new_text, source, tag)
            self._display_order.append(idx)
            self._tree.insert('', 'end', iid=str(idx),
                              values=(old_name, new_text, source),
                              tags=(tag,))

        self._configure_tags()
        self._update_status()

    def _sort_by(self, col: str):
        col_index = {'Current name': 0, 'New name': 1, 'Source': 2}[col]
        if self._sort_col == col:
            self._sort_asc = not self._sort_asc
        else:
            self._sort_col = col
            self._sort_asc = True

        self._display_order.sort(
            key=lambda i: self._row_cache[i][col_index].lower(),
            reverse=not self._sort_asc)

        arrow = ' ▲' if self._sort_asc else ' ▼'
        for c in ('Current name', 'New name', 'Source'):
            self._tree.heading(c, text=c + (arrow if c == col else ''),
                               command=lambda cv=c: self._sort_by(cv))

        self._apply_filter()

    def _configure_tags(self):
        t = self._theme
        dark = (t is _DARK)
        self._tree.tag_configure('rename',
            background=t['tree_bg'], foreground=t['tree_fg'])
        self._tree.tag_configure('ignored',
            background='#3a3a3c' if dark else '#f0f0f0',
            foreground='#666666' if dark else '#aaaaaa')
        self._tree.tag_configure('skip',
            background='#2c2c2e' if dark else '#f5f5f5',
            foreground='#666666' if dark else '#888888')
        self._tree.tag_configure('same',
            background='#2c2c2e' if dark else '#f5f5f5',
            foreground='#666666' if dark else '#888888')
        self._tree.tag_configure('conflict',
            background='#3d2a00' if dark else '#fff3e0',
            foreground='#ffaa44' if dark else '#b84c00')
        self._tree.tag_configure('done',
            background='#1a3a24' if dark else '#d4edda',
            foreground='#4cde7a' if dark else '#155724')

    def _apply_filter(self):
        term = self._filter_var.get().lower()
        for row in self._tree.get_children():
            self._tree.delete(row)
        for idx in self._display_order:
            old_name, new_text, source, base_tag = self._row_cache[idx]
            if term and term not in old_name.lower() and term not in new_text.lower():
                continue
            tag = 'ignored' if idx in self._ignored else base_tag
            self._tree.insert('', 'end', iid=str(idx),
                              values=(old_name, new_text, source),
                              tags=(tag,))
        self._configure_tags()

    def _toggle_all(self):
        if len(self._ignored) < len(self._renameable):
            for idx in self._renameable:
                self._ignored.add(idx)
                if self._tree.exists(str(idx)):
                    self._tree.item(str(idx), tags=('ignored',))
        else:
            for idx in self._renameable:
                self._ignored.discard(idx)
                if self._tree.exists(str(idx)):
                    self._tree.item(str(idx), tags=('rename',))
        self._update_status()

    def _update_status(self):
        active = len(self._renameable) - len(self._ignored)
        total  = len(self._results)
        self._status.set(
            f'{total} PDF{"s" if total != 1 else ""} found — '
            f'{active} will be renamed. '
            f'Click to ignore/un-ignore · Double-click new name to edit.')
        self._rename_btn.config(state='normal' if active > 0 else 'disabled')
        self._csv_btn.config(state='normal' if self._results else 'disabled')
        if self._renameable:
            all_ignored = len(self._ignored) == len(self._renameable)
            self._toggle_btn.config(
                state='normal',
                text='Select All' if all_ignored else 'Deselect All')
        else:
            self._toggle_btn.config(state='disabled', text='Deselect All')

    # ── export ───────────────────────────────────────────────────────────────

    def _export_csv(self):
        save_path = filedialog.asksaveasfilename(
            title='Save CSV', defaultextension='.csv',
            filetypes=[('CSV files', '*.csv'), ('All files', '*.*')],
            parent=self)
        if not save_path:
            return
        with open(save_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['Original name', 'New name', 'Source', 'Status'])
            for idx, r in enumerate(self._results):
                if r['new_name'] is None:
                    status = 'skipped (no title)'
                elif r['same']:
                    status = 'already correct'
                elif idx in self._ignored:
                    status = 'ignored'
                else:
                    status = 'will rename'
                writer.writerow([
                    r['old_path'].name,
                    r['new_name'] or '',
                    r['source'],
                    status,
                ])
        messagebox.showinfo('Exported', f'CSV saved to:\n{save_path}')

    # ── rename ────────────────────────────────────────────────────────────────

    def _do_rename(self):
        self._close_editor(save=False)
        renamed, errors = 0, []
        self._undo_log.clear()

        for idx, r in enumerate(self._results):
            if idx not in self._renameable or idx in self._ignored:
                continue
            try:
                r['old_path'].rename(r['new_path'])
                self._undo_log.append((r['new_path'], r['old_path']))
                renamed += 1
                if self._tree.exists(str(idx)):
                    self._tree.item(str(idx), tags=('done',))
            except Exception as e:
                errors.append(f"{r['old_path'].name}: {e}")

        msg = f'Done. {renamed} file{"s" if renamed != 1 else ""} renamed.'
        if errors:
            msg += f'\n\n{len(errors)} error(s):\n' + '\n'.join(errors)
            messagebox.showwarning('Completed with errors', msg)
        else:
            messagebox.showinfo('Done', msg)

        self._status.set(msg.splitlines()[0])
        self._rename_btn.config(state='disabled')
        if self._undo_log:
            self._undo_btn.config(state='normal')

    def _do_undo(self):
        if not self._undo_log:
            return
        errors = []
        for new_path, old_path in self._undo_log:
            try:
                new_path.rename(old_path)
            except Exception as e:
                errors.append(f"{new_path.name}: {e}")

        if errors:
            messagebox.showwarning('Undo errors', '\n'.join(errors))
        else:
            messagebox.showinfo('Undo complete', f'{len(self._undo_log)} file(s) restored to original names.')

        self._undo_log.clear()
        self._undo_btn.config(state='disabled')
        self._status.set('Undo complete. Scan the folder again to refresh.')


if __name__ == '__main__':
    app = App()
    # Force the window to render fully before activating
    app.update_idletasks()
    app.update()
    # Tell macOS to bring this process to the front (synchronous)
    try:
        subprocess.run(
            ['osascript', '-e',
             f'tell application "System Events" to set frontmost of '
             f'(first process whose unix id is {os.getpid()}) to true'],
            timeout=2
        )
    except Exception:
        pass
    app.activate()
    app.mainloop()
