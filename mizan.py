"""Her formattaki mizan dosyasını okuyup kebir (3 haneli) bakiyelerine indirger."""
import csv
import re
from pathlib import Path

import pandas as pd

ROLLER = ["kod", "ad", "borc", "alacak", "borc_devir", "alacak_devir", "bakiye_borc", "bakiye_alacak", "bakiye", "ba"]
ROL_AD = {"kod": "Hesap Kodu", "ad": "Hesap Adı", "borc": "Borç (toplam)", "alacak": "Alacak (toplam)",
          "borc_devir": "Devir Borç (toplam yoksa eklenir)", "alacak_devir": "Devir Alacak (toplam yoksa eklenir)",
          "bakiye_borc": "Borç Bakiye", "bakiye_alacak": "Alacak Bakiye", "bakiye": "Bakiye (tek sütun)",
          "ba": "B/A işareti"}
DEVIR = ("devir", "acilis", "donembasi", "onceki")
HARIC = ("doviz", "dvz", "miktar", "giren", "cikan", "kalan", "birim", "kur", "usd", "eur")


def sade(s):
    """Türkçe harfleri sadeleştir, yalnız harf/rakam bırak: 'Borç Bakiye' -> 'borcbakiye'."""
    s = str(s).replace("İ", "i").replace("I", "ı").lower()
    for a, b in zip("çğıöşüâî", "cgiosuai"):
        s = s.replace(a, b)
    return re.sub(r"[^a-z0-9]", "", s)


def sayi(v):
    """'1.234.567,89' / '1,234,567.89' / '(1.250,00)' / '1.250,00 A' / 1250.0 -> float."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if not s or s in ("-", "nan", "None"):
        return 0.0
    eksi = s.startswith("(") and s.endswith(")") or s.startswith("-") or s.endswith("-")
    s = re.sub(r"[^0-9,\.]", "", s)
    if not s:
        return 0.0
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    elif "," in s:  # tek virgül = ondalık (TR), çok virgül = binlik
        s = s.replace(",", ".") if s.count(",") == 1 else s.replace(",", "")
    elif s.count(".") > 1 or re.fullmatch(r"\d{1,3}\.\d{3}", s):  # çok nokta / '500.000' = binlik (TR)
        s = s.replace(".", "")
    try:
        f = float(s)
    except ValueError:
        return 0.0
    return -f if eksi else f


def kod_sade(v):
    """Hesap kodunu yalnız rakamlara indir; 3 haneden kısa veya rakamla başlamıyorsa None."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    s = str(v).strip()
    if isinstance(v, float) and v.is_integer():
        s = str(int(v))
    if not re.match(r"^\d{3}", s):
        return None
    return re.sub(r"\D", "", s)


def ham_oku(yol):
    """Dosyayı başlıksız ham tablo (DataFrame) olarak oku."""
    yol = Path(yol)
    uz = yol.suffix.lower()
    if uz in (".csv", ".txt"):
        metin = None
        for enc in ("utf-8-sig", "cp1254", "latin-1"):
            try:
                metin = yol.read_text(encoding=enc)
                break
            except UnicodeDecodeError:
                continue
        lehce = csv.Sniffer().sniff(metin[:5000], delimiters=";,\t|")
        return pd.DataFrame(list(csv.reader(metin.splitlines(), lehce)))
    sayfalar = pd.read_excel(yol, sheet_name=None, header=None, dtype=object)
    # Birden çok sayfa varsa en çok hesap kodu içereni seç
    return max(sayfalar.values(), key=lambda df: sum(kod_sade(x) is not None for x in df.iloc[:, :6].values.ravel()))


def sutun_bul(df):
    """Başlık satırını ve sütun rollerini tahmin et -> (baslik_satiri, {rol: sütun_no})."""
    en_iyi = (0, -1, {})
    for i in range(min(40, len(df))):
        basliklar = [sade(x) for x in df.iloc[i].tolist()]
        es = rol_eslestir(basliklar)
        puan = len(es) + (2 if "kod" in es else 0)
        if puan > en_iyi[0]:
            en_iyi = (puan, i, es)
    _, satir, es = en_iyi
    if "kod" not in es:  # başlık yoksa: kod gibi görünen değerlerin en çok olduğu sütun
        sayac = [sum(kod_sade(x) is not None for x in df.iloc[:, j]) for j in range(df.shape[1])]
        if max(sayac, default=0) > 0:
            es["kod"] = sayac.index(max(sayac))
    return satir, es


def rol_eslestir(basliklar):
    es = {}
    adaylar = {"borc": [], "alacak": []}
    for j, b in enumerate(basliklar):
        if not b or any(h in b for h in HARIC):
            continue
        if "bakiye" in b or b in ("bb", "ab", "borcbky", "alacakbky"):
            if "borc" in b or b == "bb":
                es.setdefault("bakiye_borc", j)
            elif "alacak" in b or b == "ab":
                es.setdefault("bakiye_alacak", j)
            elif "tur" in b or "yon" in b or b in ("bakiyeba", "ba"):
                es.setdefault("ba", j)
            else:
                es.setdefault("bakiye", j)
        elif b in ("ba", "borcalacak", "bta", "durum") and "ba" not in es:
            es["ba"] = j
        elif "borc" in b:
            adaylar["borc"].append((b, j))
        elif "alacak" in b:
            adaylar["alacak"].append((b, j))
        elif ("kod" in b or b in ("hesapno", "hesap", "hesapnumarasi")) and "kod" not in es:
            es["kod"] = j
        elif ("ad" in b or "aciklama" in b or "unvan" in b or "isim" in b) and "ad" not in es:
            es["ad"] = j
    for rol, liste in adaylar.items():
        if not liste:
            continue
        # 'Toplam Borç' varsa yalnız o. Yoksa dönem sütunu + ayrı devir sütunu (ERP'ler devir/dönem ayırır)
        toplam = [j for b, j in liste if "toplam" in b or "genel" in b]
        devir = [j for b, j in liste if any(d in b for d in DEVIR)]
        donem = [j for b, j in liste if not any(d in b for d in DEVIR)]
        if toplam:
            es[rol] = toplam[-1]
        elif donem:
            es[rol] = donem[-1]
            if devir:
                es[rol + "_devir"] = devir[0]
        else:
            es[rol] = liste[-1][1]
    return es


def kebire_indir(df, satir, es):
    """Eşleştirmeyle satırları oku, alt hesapları kebire topla.
    Dönüş: (hesaplar {kebir: {'ad', 'bakiye', 'kaynak_bakiye'}}, uyarılar [str])."""
    if "kod" not in es:
        raise ValueError("Hesap kodu sütunu bulunamadı.")
    yontem = ("borc" in es and "alacak" in es and "borc_alacak") or \
             ("bakiye_borc" in es and "bakiye_alacak" in es and "bakiye_ayri") or \
             ("bakiye" in es and "bakiye_tek") or None
    if not yontem:
        raise ValueError("Borç/Alacak veya Bakiye sütunları bulunamadı.")

    def al(row, rol):
        return row[es[rol]] if rol in es else None

    uyarilar = []
    baslik = [sade(x) for x in df.iloc[satir].tolist()]
    if yontem == "borc_alacak":
        b_borc = baslik[es["borc"]] if es["borc"] < len(baslik) else ""
        devirli = any(d in b for b in baslik for d in DEVIR)
        if "borc_devir" in es or "alacak_devir" in es:
            uyarilar.append("Mizanda toplam sütunu yok: devir + dönem borç/alacak sütunları toplandı.")
        elif devirli and not ("toplam" in b_borc or "genel" in b_borc) and not any(d in b_borc for d in DEVIR):
            uyarilar.append("Mizanda devir sütunu var ama eşleştirilemedi: seçilen borç/alacak yalnız dönem "
                            "hareketi olabilir (açılış bakiyeleri eksik kalır, bilanço yine dengeli görünür). "
                            "Sütunları Düzelt ile devir sütunlarını seçin.")

    satirlar = []
    for row in df.iloc[satir + 1:].itertuples(index=False):
        kod = kod_sade(al(row, "kod"))
        if not kod:
            continue
        ad = al(row, "ad")
        borc = alacak = None
        if yontem == "borc_alacak":
            borc = sayi(al(row, "borc")) + sayi(al(row, "borc_devir"))
            alacak = sayi(al(row, "alacak")) + sayi(al(row, "alacak_devir"))
            bak = borc - alacak
        elif yontem == "bakiye_ayri":
            bak = sayi(al(row, "bakiye_borc")) - sayi(al(row, "bakiye_alacak"))
        else:
            bak = sayi(al(row, "bakiye"))
            if "ba" in es and sade(al(row, "ba")).startswith("a"):
                bak = -abs(bak)
        kontrol = []  # aynı satırdaki diğer bakiye sütunları (çapraz kontrol için)
        if yontem == "borc_alacak":
            if "bakiye_borc" in es and "bakiye_alacak" in es:
                kontrol.append(("Borç/Alacak Bakiye", sayi(al(row, "bakiye_borc")) - sayi(al(row, "bakiye_alacak"))))
            if "bakiye" in es and "ba" not in es:
                kontrol.append(("Bakiye", sayi(al(row, "bakiye"))))
        satirlar.append((kod, "" if ad is None or (isinstance(ad, float) and pd.isna(ad)) else str(ad).strip(), bak, kontrol, borc, alacak))

    if yontem == "bakiye_tek" and "ba" not in es and satirlar and all(x[2] >= 0 for x in satirlar):
        uyarilar.append("Tek 'Bakiye' sütununda eksi işaret ve B/A sütunu yok: alacak bakiyeli hesaplar borç "
                        "sayıldı. B/A sütununu eşleştirin ya da borç/alacak sütunlu mizan yükleyin.")
    # Aynı kebir altında hem üst hem alt hesap varsa yalnız en üst seviyeyi say (çift sayımı önle)
    kodlar = {k for k, *_ in satirlar}
    hesaplar = {}
    for kod, ad, bak, kontrol, borc, alacak in satirlar:
        if any(kod != u and kod.startswith(u) for u in kodlar if len(u) < len(kod)):
            continue
        keb = kod[:3]
        h = hesaplar.setdefault(keb, {"ad": "", "bakiye": 0.0, "kontrol": {}})
        h["bakiye"] += bak
        if borc is not None:  # hareket toplamları: envanter sistemini tanımak için (motor.envanter_analiz)
            h["borc"] = h.get("borc", 0.0) + borc
            h["alacak"] = h.get("alacak", 0.0) + alacak
        if kod == keb or not h["ad"]:
            h["ad"] = ad if kod == keb else (h["ad"] or ad)
        for sut, v in kontrol:
            h["kontrol"][sut] = h["kontrol"].get(sut, 0.0) + v
    for keb, h in sorted(hesaplar.items()):
        for sut, v in h["kontrol"].items():
            if abs(v - h["bakiye"]) > 0.05:
                uyarilar.append(f"{keb} {h['ad']}: mizandaki '{sut}' sütunu {tl(v)}, "
                                f"borç−alacak {tl(h['bakiye'])}. Borç−alacak esas alındı.")
    return hesaplar, uyarilar


def tl(x):
    return f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def oku(yol, es=None, satir=None):
    """Kolay yol: dosya -> (hesaplar, uyarılar, (ham_df, satir, es))."""
    df = ham_oku(yol)
    if es is None:
        satir, es = sutun_bul(df)
    hesaplar, uyarilar = kebire_indir(df, satir, es)
    return hesaplar, uyarilar, (df, satir, es)
