"""Firma / dönem kayıtları ve iki dönem karşılaştırması (08.11.2026, Kenan Bey isteği).

Her kayıt tek JSON dosyası: <kök>/<firma>/<dönem>.json
  {"firma", "donem", "kayit_tarihi", "kaynak_dosya", "hesaplar": {kebir: {ad, bakiye}}, "girdiler": {alan: metin}}
Kök varsayılanı: Belgeler/Başkan Kayıtlar (yedeklenebilir, elle taşınabilir).
"""
import json
import re
import time
from pathlib import Path

KOK = Path.home() / "Documents" / "Başkan Kayıtlar"


def _ad(s):
    """Dosya adı için güvenli (Windows yasaklı karakterleri ayıkla)."""
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", s.strip())[:80] or "adsiz"


def kaydet(firma, donem, hesaplar, girdiler, kaynak_dosya="", kok=None):
    kok = Path(kok or KOK)
    d = kok / _ad(firma)
    d.mkdir(parents=True, exist_ok=True)
    yol = d / f"{_ad(donem)}.json"
    veri = {"firma": firma.strip(), "donem": donem.strip(), "kayit_tarihi": time.strftime("%Y-%m-%d %H:%M"),
            "kaynak_dosya": kaynak_dosya, "hesaplar": hesaplar, "girdiler": girdiler}
    gecici = yol.with_suffix(".tmp")
    gecici.write_text(json.dumps(veri, ensure_ascii=False, indent=1), encoding="utf-8")
    gecici.replace(yol)
    return yol


def liste(kok=None):
    """[(firma, dönem, kayıt tarihi, yol)] — firma, sonra dönem sırasıyla."""
    kok = Path(kok or KOK)
    out = []
    for f in sorted(kok.glob("*/*.json")):
        try:
            v = json.loads(f.read_text(encoding="utf-8"))
            out.append((v["firma"], v["donem"], v.get("kayit_tarihi", ""), f))
        except (ValueError, KeyError, OSError):
            continue
    return sorted(out, key=lambda x: (x[0].lower(), x[1]))


def oku(yol):
    return json.loads(Path(yol).read_text(encoding="utf-8"))


def sil(yol):
    Path(yol).unlink(missing_ok=True)


def karsilastir(r1, r2):
    """İki motor sonucunu kalem kalem hizalar → {'gelir': satırlar, 'bilanco': satırlar, 'ozet': satırlar}.
    Satır: (tür, kod, ad, d1, d2, fark, değişim_oranı)."""
    def hizala(s1, s2):
        anahtar = lambda tur, kod, ad: (tur, kod, ad.strip())
        sira, d1, d2 = [], {}, {}
        for kaynak, hedef in ((s1, d1), (s2, d2)):
            for tur, kod, ad, t in kaynak:
                k = anahtar(tur, kod, ad)
                if k not in d1 and k not in d2:
                    sira.append(k)
                hedef[k] = t
        out = []
        for k in sira:
            a, b = d1.get(k), d2.get(k)
            fark = (b or 0.0) - (a or 0.0) if (a is not None or b is not None) else None
            oran = fark / abs(a) if a else None
            out.append((k[0], k[1], k[2], a, b, fark, oran))
        return out

    bil1 = [x for x in r1["aktif"]] + [x for x in r1["pasif"]]
    bil2 = [x for x in r2["aktif"]] + [x for x in r2["pasif"]]
    vergi = lambda r: [("kalem", "", ad, t) for ad, t in r["vergi"]] + [("kalem", "", ad, t) for ad, t in r["rasyo"]]
    return {"gelir": hizala(r1["gelir_tablosu"], r2["gelir_tablosu"]),
            "bilanco": hizala(bil1, bil2),
            "ozet": hizala(vergi(r1), vergi(r2))}


def sina():
    import tempfile
    k = tempfile.mkdtemp()
    y = kaydet("ABC Ltd.", "2026/09", {"100": {"ad": "KASA", "bakiye": 5.0}}, {"stok153": "10"}, kok=k)
    kaydet("ABC Ltd.", "2026/06", {"100": {"ad": "KASA", "bakiye": 3.0}}, {}, kok=k)
    kaydet("XYZ A.Ş.", "2025/12", {}, {}, kok=k)
    l = liste(k)
    assert [(f, d) for f, d, *_ in l] == [("ABC Ltd.", "2026/06"), ("ABC Ltd.", "2026/09"), ("XYZ A.Ş.", "2025/12")], l
    assert oku(y)["girdiler"]["stok153"] == "10"
    kaydet("ABC Ltd.", "2026/09", {"100": {"ad": "KASA", "bakiye": 7.0}}, {}, kok=k)   # aynı dönem: üzerine yazar
    assert oku(y)["hesaplar"]["100"]["bakiye"] == 7.0 and len(liste(k)) == 3
    r = {"gelir_tablosu": [("bolum", "A", "BRÜT SATIŞLAR", 100.0)], "aktif": [("kalem", "100", "KASA", 10.0)],
         "pasif": [], "vergi": [], "rasyo": []}
    r2 = {"gelir_tablosu": [("bolum", "A", "BRÜT SATIŞLAR", 150.0)], "aktif": [("kalem", "102", "BANKA", 4.0)],
          "pasif": [], "vergi": [], "rasyo": []}
    k_ = karsilastir(r, r2)
    assert k_["gelir"][0][3:] == (100.0, 150.0, 50.0, 0.5)
    assert ("kalem", "102", "BANKA", None, 4.0, 4.0, None) in k_["bilanco"]
    print("kayit sına: tamam")


if __name__ == "__main__":
    sina()
