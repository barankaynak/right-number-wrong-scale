# Pre-registration tags

The paper and `PREREGISTRATION.md` refer to these git tags of the development repository, which is not public. Each row gives the commit the tag points to and its date. To check a frozen file, compare its SHA-256 (LF line endings) in this archive with the row in `PREREGISTRATION.md`; files changed by a later frozen version differ, and files sanitised for release are listed in `RELEASE_NOTE.md`.

| tag | commit | date |
|---|---|---|
| prereg-v1.0 | 201e04f | 2026-07-08 |
| prereg-v2.0 | 16d0cf5 | 2026-07-10 |
| prereg-v3.0 | 7aa5a79 | 2026-10-14 |
| prereg-v3.1 | d42ce9e | 2026-10-14 |
| prereg-v3.2 | 7ee8569 | 2026-10-14 |
| prereg-v3.3 | c4bf3bb | 2026-10-14 |
| prereg-v3.4 | ae98f99 | 2026-11-05 |
| prereg-v3.5 | d1a7667 | 2026-11-05 |
| prereg-v3.6 | f51bb96 | 2026-11-05 |
| prereg-v3.7 | adad4c0 | 2026-11-05 |
| prereg-v3.8 | c0d263b | 2026-11-14 |

## The 156 hash rows of `PREREGISTRATION.md`

Checked against the development repository's history before release:

- 123 rows equal the file in this archive.
- 23 rows are superseded by a later row for the same file, which equals the file here.
- 4 rows equal an earlier committed version of a file that a later frozen version changed, as
  `PREREGISTRATION.md` records (`inject_errors.py` once, `crosslingual_stats.py` three times).
- 2 rows name the staging path of `scale_assertion_analysis.py`; the file was moved byte-identical
  to `experiments/gfp_benchmark/` and equals those rows there.
- 2 rows name files that `PREREGISTRATION.md` marks as kept outside git
  (`coding_interface_v4/coder2.html`, `patch_v4_subset.py`). They are not in this archive.
- 2 rows belong to the A8 precision audit, which was withdrawn and never run
  (`a8_precision/WITHDRAWN.md`). They were hashed on the generator's output as written to disk:
  Python's `csv` module ends rows with CRLF, while cells keep their own LF line breaks; git stored
  the files with LF row ends. Restoring the CRLF row ends reproduces both hashes:

```python
import csv, hashlib, io
for f in ("A8_coding_sheet.csv", "A8_guard_key.csv"):
    rows = list(csv.reader(io.StringIO(open(f, encoding="utf-8-sig", newline="").read(), newline="")))
    buf = io.StringIO(newline=""); csv.writer(buf).writerows(rows)
    print(f, hashlib.sha256(("\ufeff" + buf.getvalue()).encode("utf-8")).hexdigest())
```
