"""
Builds the site into _site/:
  - copies index.html, CNAME and the original photos unchanged (full quality)
  - creates light thumbnails for the gallery grid (thumbs/)
  - writes photos.json listing every photo, newest first
Runs automatically on GitHub (see .github/workflows/deploy.yml).
"""
import hashlib, json, os, shutil, subprocess, sys
from pathlib import Path
from PIL import Image, ImageOps

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
OUT = ROOT / "_site"
CACHE = ROOT / ".thumbcache"
CATEGORIES = ["edited", "original", "bw"]
EXTS = {".jpg", ".jpeg", ".png", ".webp"}
THUMB_EDGE = 1000      # px, long edge of grid thumbnails
THUMB_QUALITY = 82


def commit_time(path):
    try:
        out = subprocess.run(["git", "log", "-1", "--format=%ct", "--", str(path)],
                             cwd=ROOT, capture_output=True, text=True).stdout.strip()
        return int(out) if out else int(path.stat().st_mtime)
    except Exception:
        return int(path.stat().st_mtime)


def make_thumb(src, dst):
    with Image.open(src) as im:
        icc = im.info.get("icc_profile")
        im = ImageOps.exif_transpose(im)
        if im.mode not in ("RGB", "L"):
            im = im.convert("RGB")
        im.thumbnail((THUMB_EDGE, THUMB_EDGE), Image.LANCZOS)
        kw = dict(quality=THUMB_QUALITY, optimize=True, progressive=True)
        if icc:
            kw["icc_profile"] = icc
        im.save(dst, "JPEG", **kw)
        return im.size


if OUT.exists():
    shutil.rmtree(OUT)
(OUT / "thumbs").mkdir(parents=True)
CACHE.mkdir(exist_ok=True)

for f in ["index.html", "CNAME"]:
    if (ROOT / f).exists():
        shutil.copy2(ROOT / f, OUT / f)

photos = []
for cat in CATEGORIES:
    folder = ROOT / "photos" / cat
    if not folder.is_dir():
        continue
    (OUT / "photos" / cat).mkdir(parents=True, exist_ok=True)
    for p in sorted(folder.iterdir()):
        if p.suffix.lower() not in EXTS or not p.is_file():
            continue
        shutil.copy2(p, OUT / "photos" / cat / p.name)          # original, untouched
        digest = hashlib.sha1(p.read_bytes()).hexdigest()[:16]
        thumb_name = f"{digest}.jpg"
        cached = CACHE / thumb_name
        meta = CACHE / f"{digest}.json"
        if cached.exists() and meta.exists():
            w, h = json.loads(meta.read_text())
        else:
            try:
                w, h = make_thumb(p, cached)
            except Exception as e:
                print(f"skip {p}: {e}")
                continue
            meta.write_text(json.dumps([w, h]))
        shutil.copy2(cached, OUT / "thumbs" / thumb_name)
        photos.append({
            "src": f"photos/{cat}/{p.name}",
            "thumb": f"thumbs/{thumb_name}",
            "cat": cat,
            "w": w, "h": h,
            "t": commit_time(p),
        })

photos.sort(key=lambda x: x["t"], reverse=True)
(OUT / "photos.json").write_text(json.dumps(photos, ensure_ascii=False))
print(f"built {len(photos)} photos")
