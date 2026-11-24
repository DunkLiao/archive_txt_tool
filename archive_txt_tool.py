# -*- coding: utf-8 -*-
# ==========================================================================
# 壓縮檔批次解壓縮 + 副檔名加 .txt / 還原 工具 (tkinter / ttk)
#
# 功能
#   1. 指定「來源資料夾」與「目的資料夾」
#   2. 解壓縮來源資料夾內所有壓縮檔，每個壓縮檔解壓到「目的資料夾\壓縮檔檔名\」
#   3. 目的資料夾(含子目錄)所有檔案：a.html -> a.html.txt
#   4. 還原：a.html.txt -> a.html
#
# 支援格式：zip, tar, tar.gz, tgz, tar.bz2, tar.xz, gz
#           7z (需安裝 py7zr)、rar (需安裝 rarfile 且系統有 unrar)
#
# 執行方式：存成 archive_txt_tool.py 後，在命令列執行
#           python archive_txt_tool.py
# ==========================================================================
import os
import queue
import shutil
import tarfile
import threading
import zipfile
import gzip
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

try:
    import py7zr  # type: ignore
except Exception:  # pragma: no cover
    py7zr = None
try:
    import rarfile  # type: ignore
except Exception:  # pragma: no cover
    rarfile = None

# 由長到短排列，避免 .tar.gz 被當成 .gz
ARCHIVE_SUFFIXES = [
    ".tar.gz", ".tar.bz2", ".tar.xz",
    ".tgz", ".tbz2", ".txz",
    ".zip", ".tar", ".gz", ".7z", ".rar",
]
TXT = ".txt"


# --------------------------------------------------------------------------
# 核心邏輯 (與 GUI 分離，方便測試)
# --------------------------------------------------------------------------
def archive_suffix(filename):
    """回傳壓縮檔副檔名，非壓縮檔回傳 None"""
    low = filename.lower()
    for suf in ARCHIVE_SUFFIXES:
        if low.endswith(suf):
            return suf
    return None


def find_archives(src, recursive=True):
    result = []
    if recursive:
        for root, _dirs, files in os.walk(src):
            for f in sorted(files):
                if archive_suffix(f):
                    result.append(os.path.join(root, f))
    else:
        for f in sorted(os.listdir(src)):
            p = os.path.join(src, f)
            if os.path.isfile(p) and archive_suffix(f):
                result.append(p)
    return result


def unique_dir(path):
    """若資料夾已存在則加 _1, _2 ..."""
    if not os.path.exists(path):
        return path
    i = 1
    while os.path.exists(f"{path}_{i}"):
        i += 1
    return f"{path}_{i}"


def unique_file(path):
    if not os.path.exists(path):
        return path
    base, ext = os.path.splitext(path)
    i = 1
    while os.path.exists(f"{base}_{i}{ext}"):
        i += 1
    return f"{base}_{i}{ext}"


def safe_join(base, name):
    """防止 Zip Slip：確認解壓路徑在 base 之內"""
    name = name.replace("\\", "/").lstrip("/")
    target = os.path.abspath(os.path.join(base, name))
    base_abs = os.path.abspath(base)
    if target != base_abs and not target.startswith(base_abs + os.sep):
        raise ValueError(f"不安全的路徑: {name}")
    return target


def fix_zip_name(info):
    """修正 zip 內中文檔名亂碼 (未標示 UTF-8 時，zipfile 以 cp437 解碼)"""
    name = info.filename
    if info.flag_bits & 0x800:
        return name
    try:
        raw = name.encode("cp437")
    except UnicodeEncodeError:
        return name
    for enc in ("utf-8", "cp950", "gbk", "cp932"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return name


def extract_zip(path, out_dir):
    count = 0
    with zipfile.ZipFile(path) as zf:
        for info in zf.infolist():
            name = fix_zip_name(info)
            target = safe_join(out_dir, name)
            if info.is_dir() or name.endswith("/"):
                os.makedirs(target, exist_ok=True)
                continue
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with zf.open(info) as s, open(target, "wb") as d:
                shutil.copyfileobj(s, d)
            count += 1
    return count


def extract_tar(path, out_dir):
    count = 0
    with tarfile.open(path) as tf:
        for m in tf.getmembers():
            target = safe_join(out_dir, m.name)  # 檢查路徑
            if m.isdir():
                os.makedirs(target, exist_ok=True)
            elif m.isfile():
                os.makedirs(os.path.dirname(target), exist_ok=True)
                s = tf.extractfile(m)
                if s is not None:
                    with s, open(target, "wb") as d:
                        shutil.copyfileobj(s, d)
                    count += 1
            # 連結、裝置檔等一律略過
    return count


def extract_gz(path, out_dir):
    name = os.path.basename(path)[:-3] or "file"
    target = os.path.join(out_dir, name)
    with gzip.open(path, "rb") as s, open(target, "wb") as d:
        shutil.copyfileobj(s, d)
    return 1


def extract_7z(path, out_dir):
    if py7zr is None:
        raise RuntimeError("未安裝 py7zr，無法解壓縮 .7z (pip install py7zr)")
    with py7zr.SevenZipFile(path) as z:
        names = z.getnames()
        for n in names:
            safe_join(out_dir, n)
        z.extractall(out_dir)
    return len(names)


def extract_rar(path, out_dir):
    if rarfile is None:
        raise RuntimeError("未安裝 rarfile，無法解壓縮 .rar (pip install rarfile，且需有 unrar)")
    with rarfile.RarFile(path) as rf:
        for n in rf.namelist():
            safe_join(out_dir, n)
        rf.extractall(out_dir)
        return len(rf.namelist())


def extract_archive(path, out_dir):
    suf = archive_suffix(os.path.basename(path))
    os.makedirs(out_dir, exist_ok=True)
    if suf == ".zip":
        return extract_zip(path, out_dir)
    if suf in (".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tbz2", ".tar.xz", ".txz"):
        return extract_tar(path, out_dir)
    if suf == ".gz":
        return extract_gz(path, out_dir)
    if suf == ".7z":
        return extract_7z(path, out_dir)
    if suf == ".rar":
        return extract_rar(path, out_dir)
    raise RuntimeError(f"不支援的格式: {path}")


def iter_files(root):
    for r, _d, files in os.walk(root):
        for f in files:
            yield os.path.join(r, f)


def add_txt(dest, log=print, progress=None):
    """目的資料夾所有檔案加上 .txt (已是 .txt 結尾者略過，避免重複點擊變成 .txt.txt)"""
    files = list(iter_files(dest))
    ok = skip = fail = 0
    for i, p in enumerate(files, 1):
        if p.lower().endswith(TXT):
            skip += 1
        else:
            new = p + TXT
            try:
                if os.path.exists(new):
                    raise FileExistsError("目標檔名已存在")
                os.rename(p, new)
                ok += 1
            except Exception as e:
                fail += 1
                log(f"[失敗] {p}: {e}")
        if progress:
            progress(i, len(files))
    return ok, skip, fail


def remove_txt(dest, log=print, progress=None):
    """目的資料夾所有 .txt 結尾的檔案去除 .txt"""
    files = list(iter_files(dest))
    ok = skip = fail = 0
    for i, p in enumerate(files, 1):
        if not p.lower().endswith(TXT):
            skip += 1
        else:
            new = p[: -len(TXT)]
            try:
                if os.path.exists(new):
                    raise FileExistsError("目標檔名已存在")
                os.rename(p, new)
                ok += 1
            except Exception as e:
                fail += 1
                log(f"[失敗] {p}: {e}")
        if progress:
            progress(i, len(files))
    return ok, skip, fail


# --------------------------------------------------------------------------
# GUI
# --------------------------------------------------------------------------
class App(ttk.Frame):
    def __init__(self, master):
        super().__init__(master, padding=12)
        self.master = master
        master.title("壓縮檔解壓縮 / 副檔名 .txt 轉換工具")
        master.geometry("820x600")
        master.minsize(700, 500)
        self.pack(fill="both", expand=True)

        self.src_var = tk.StringVar()
        self.dst_var = tk.StringVar()
        self.recursive_var = tk.BooleanVar(value=True)
        self.auto_txt_var = tk.BooleanVar(value=False)
        self.q = queue.Queue()
        self.busy = False

        self._build()
        self.after(100, self._poll)

    # ---- UI ----
    def _build(self):
        self.columnconfigure(1, weight=1)

        ttk.Label(self, text="來源資料夾：").grid(row=0, column=0, sticky="e", pady=4)
        ttk.Entry(self, textvariable=self.src_var).grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Button(self, text="瀏覽...", command=lambda: self._browse(self.src_var)).grid(row=0, column=2)

        ttk.Label(self, text="目的資料夾：").grid(row=1, column=0, sticky="e", pady=4)
        ttk.Entry(self, textvariable=self.dst_var).grid(row=1, column=1, sticky="ew", padx=6)
        ttk.Button(self, text="瀏覽...", command=lambda: self._browse(self.dst_var)).grid(row=1, column=2)

        opt = ttk.Frame(self)
        opt.grid(row=2, column=1, columnspan=2, sticky="w", pady=2)
        ttk.Checkbutton(opt, text="包含來源子資料夾內的壓縮檔", variable=self.recursive_var).pack(side="left")
        ttk.Checkbutton(opt, text="解壓縮後自動加上 .txt", variable=self.auto_txt_var).pack(side="left", padx=16)

        btns = ttk.LabelFrame(self, text="操作", padding=8)
        btns.grid(row=3, column=0, columnspan=3, sticky="ew", pady=8)
        self.btn_extract = ttk.Button(btns, text="① 解壓縮", command=self.on_extract)
        self.btn_add = ttk.Button(btns, text="② 副檔名加 .txt", command=self.on_add)
        self.btn_restore = ttk.Button(btns, text="③ 還原(去除 .txt)", command=self.on_restore)
        for b in (self.btn_extract, self.btn_add, self.btn_restore):
            b.pack(side="left", padx=6)

        self.progress = ttk.Progressbar(self, mode="determinate")
        self.progress.grid(row=4, column=0, columnspan=3, sticky="ew")
        self.status = ttk.Label(self, text="就緒")
        self.status.grid(row=5, column=0, columnspan=3, sticky="w", pady=(2, 6))

        logf = ttk.LabelFrame(self, text="執行記錄", padding=4)
        logf.grid(row=6, column=0, columnspan=3, sticky="nsew")
        self.rowconfigure(6, weight=1)
        self.log_text = tk.Text(logf, height=12, wrap="none", state="disabled")
        ys = ttk.Scrollbar(logf, orient="vertical", command=self.log_text.yview)
        xs = ttk.Scrollbar(logf, orient="horizontal", command=self.log_text.xview)
        self.log_text.configure(yscrollcommand=ys.set, xscrollcommand=xs.set)
        logf.rowconfigure(0, weight=1)
        logf.columnconfigure(0, weight=1)
        self.log_text.grid(row=0, column=0, sticky="nsew")
        ys.grid(row=0, column=1, sticky="ns")
        xs.grid(row=1, column=0, sticky="ew")

    def _browse(self, var):
        d = filedialog.askdirectory(initialdir=var.get() or os.path.expanduser("~"))
        if d:
            var.set(os.path.normpath(d))

    # ---- queue / thread helpers ----
    def _poll(self):
        try:
            while True:
                kind, a, b = self.q.get_nowait()
                if kind == "log":
                    self.log_text.configure(state="normal")
                    self.log_text.insert("end", a + "\n")
                    self.log_text.see("end")
                    self.log_text.configure(state="disabled")
                elif kind == "progress":
                    self.progress["maximum"] = max(b, 1)
                    self.progress["value"] = a
                    self.status.configure(text=f"進度 {a}/{b}")
                elif kind == "done":
                    self._set_busy(False)
                    self.status.configure(text=a)
                    if b:
                        messagebox.showinfo("完成", a)
        except queue.Empty:
            pass
        self.after(100, self._poll)

    def _log(self, msg):
        self.q.put(("log", msg, None))

    def _prog(self, i, n):
        self.q.put(("progress", i, n))

    def _set_busy(self, busy):
        self.busy = busy
        st = "disabled" if busy else "normal"
        for b in (self.btn_extract, self.btn_add, self.btn_restore):
            b.configure(state=st)

    def _run(self, func):
        if self.busy:
            return
        self._set_busy(True)
        self.progress["value"] = 0
        threading.Thread(target=self._wrap, args=(func,), daemon=True).start()

    def _wrap(self, func):
        try:
            msg = func()
            self.q.put(("done", msg, True))
        except Exception as e:
            self._log(f"[錯誤] {e}")
            self.q.put(("done", f"發生錯誤：{e}", False))

    # ---- validation ----
    def _check_dst(self):
        dst = self.dst_var.get().strip()
        if not dst:
            messagebox.showwarning("提示", "請指定目的資料夾")
            return None
        if not os.path.isdir(dst):
            if messagebox.askyesno("提示", f"目的資料夾不存在，是否建立？\n{dst}"):
                try:
                    os.makedirs(dst)
                except Exception as e:
                    messagebox.showerror("錯誤", str(e))
                    return None
            else:
                return None
        return dst

    # ---- actions ----
    def on_extract(self):
        src = self.src_var.get().strip()
        if not os.path.isdir(src):
            messagebox.showwarning("提示", "請指定有效的來源資料夾")
            return
        dst = self._check_dst()
        if not dst:
            return
        if os.path.abspath(src) == os.path.abspath(dst):
            messagebox.showwarning("提示", "來源與目的資料夾不可相同")
            return
        recursive = self.recursive_var.get()
        auto_txt = self.auto_txt_var.get()
        self._run(lambda: self._do_extract(src, dst, recursive, auto_txt))

    def _do_extract(self, src, dst, recursive, auto_txt):
        archives = find_archives(src, recursive)
        if not archives:
            self._log("來源資料夾中找不到壓縮檔")
            return "找不到壓縮檔"
        self._log(f"共找到 {len(archives)} 個壓縮檔")
        ok = fail = 0
        for i, a in enumerate(archives, 1):
            base = os.path.basename(a)
            folder_name = base[: -len(archive_suffix(base))] or base
            out = unique_dir(os.path.join(dst, folder_name))
            try:
                n = extract_archive(a, out)
                self._log(f"[成功] {a} -> {out} ({n} 個檔案)")
                ok += 1
            except Exception as e:
                self._log(f"[失敗] {a}: {e}")
                fail += 1
            self._prog(i, len(archives))
        msg = f"解壓縮完成：成功 {ok}，失敗 {fail}"
        if auto_txt:
            a, s, f = add_txt(dst, self._log, self._prog)
            msg += f"；加 .txt：成功 {a}，略過 {s}，失敗 {f}"
        self._log(msg)
        return msg

    def on_add(self):
        dst = self._check_dst()
        if not dst:
            return
        if not messagebox.askyesno("確認", f"將對下列資料夾(含子目錄)所有檔案加上 .txt：\n{dst}\n\n是否繼續？"):
            return
        self._run(lambda: self._do_rename(dst, add_txt, "加 .txt"))

    def on_restore(self):
        dst = self._check_dst()
        if not dst:
            return
        if not messagebox.askyesno("確認", f"將對下列資料夾(含子目錄)所有 .txt 檔案去除 .txt：\n{dst}\n\n是否繼續？"):
            return
        self._run(lambda: self._do_rename(dst, remove_txt, "還原"))

    def _do_rename(self, dst, func, label):
        ok, skip, fail = func(dst, self._log, self._prog)
        msg = f"{label}完成：成功 {ok}，略過 {skip}，失敗 {fail}"
        self._log(msg)
        return msg


def main():
    root = tk.Tk()
    try:
        ttk.Style().theme_use("vista" if os.name == "nt" else "clam")
    except tk.TclError:
        pass
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
