"""Geometric comparison of two Gerber files, ignoring draw order, attributes and dates."""
import re, sys, collections
def load(path):
    txt = open(path).read()
    # aperture macros and definitions
    macros = {m.group(1): re.sub(r"\s+", "", m.group(2)) for m in re.finditer(r"%AM([^*]+)\*([^%]*)%", txt)}
    aps = {}
    for m in re.finditer(r"%ADD(\d+)([^,*]+)(?:,([^*]*))?\*%", txt):
        name = m.group(2)
        aps[int(m.group(1))] = (macros.get(name, name), m.group(3) or "")
    body = re.sub(r"%[^%]*%", "", txt)
    body = re.sub(r"G04[^*]*\*", "", body)
    prims = collections.Counter()
    x = y = 0; ap = None; mode = "G01"; region = False; contour = []; contours = []
    def flush():
        nonlocal contour
        if len(contour) > 1:
            pts = contour[:-1] if contour[0][:2] == contour[-1][:2] else contour
            k = min(range(len(pts)), key=lambda i: pts[i])
            a = tuple(pts[k:] + pts[:k]); b = tuple([a[0]] + list(reversed(a[1:])))
            # arcs inside regions keep their mode in the tuple, compare forward/backward by point set
            prims[("region", min(tuple(p[:2] for p in a), tuple(p[:2] for p in b)), tuple(sorted(p[2:] for p in pts)))] += 1
        contour = []
    for cmd in body.split("*"):
        cmd = cmd.strip()
        if not cmd: continue
        if cmd in ("G01", "G02", "G03"): mode = cmd; continue
        if cmd == "G36": region = True; contour = []; continue
        if cmd == "G37": flush(); region = False; continue
        if cmd in ("G75", "G74", "M02"): continue
        m = re.fullmatch(r"D(\d+)", cmd)
        if m and int(m.group(1)) >= 10: ap = aps[int(m.group(1))]; continue
        m = re.fullmatch(r"(G0[123])?(?:X(-?\d+))?(?:Y(-?\d+))?(?:I(-?\d+))?(?:J(-?\d+))?D0([123])", cmd)
        if not m: raise SystemExit("unparsed: %r in %s" % (cmd, path))
        if m.group(1): mode = m.group(1)
        nx = int(m.group(2)) if m.group(2) else x; ny = int(m.group(3)) if m.group(3) else y
        ij = (int(m.group(4) or 0), int(m.group(5) or 0)); op = m.group(6)
        if region:
            if op == "2": flush(); contour = [(nx, ny, "M")]
            else: contour.append((nx, ny, mode) + (ij if mode != "G01" else ()))
        elif op == "3": prims[("flash", ap, nx, ny)] += 1
        elif op == "1":
            if mode == "G01": prims[("line", ap) + tuple(sorted([(x, y), (nx, ny)]))] += 1
            else: prims[("arc", ap, mode, x, y, nx, ny, x + ij[0], y + ij[1])] += 1
        x, y = nx, ny
    return prims
a, b = load(sys.argv[1]), load(sys.argv[2])
only_a, only_b = a - b, b - a
print("%-45s prims %5d / %5d  only-old %d  only-new %d" % (sys.argv[1].split("-")[-1], sum(a.values()), sum(b.values()), sum(only_a.values()), sum(only_b.values())))
for k in list(only_a)[:3]: print("   old:", str(k)[:200])
for k in list(only_b)[:3]: print("   new:", str(k)[:200])
