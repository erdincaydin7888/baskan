"""Başkan çıktıları (08.11.2026, kullanıcı isteği):
  excel_formullu(r, hesaplar, yol)  → kalemler Kebir Mizan sayfasına SUMIF ile bağlı, toplam / ara satırlar formül
  rapor_html(r, baslik)             → yazıcı ve PDF için tek belge (her rapor ayrı sayfada)
r = motor.hesapla(...) sonucu, hesaplar = mizan.kebire_indir(...) sonucu (ham mizan bakiyeleri)."""
import html
import time

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

SAYI = "#,##0.00;[Red]-#,##0.00"
YUZDE = "0.00%"
RENK = {"sinif": "DBE7F5", "bolum": "DBE7F5", "grup": "EEF3F9", "ara": "FFF2CC", "toplam": "C9E4C5"}
MZ = "'Kebir Mizan'"
ARA_FORMUL = {  # gelir tablosu ara satırları: bölüm harfleri / önceki ara satırlarla
    "NET SATIŞLAR": "{A}-{B}",
    "BRÜT SATIŞ KARI / ZARARI": "{NET SATIŞLAR}-{C}",
    "FAALİYET KARI / ZARARI": "{BRÜT SATIŞ KARI / ZARARI}-{D}",
    "OLAĞAN KAR / ZARAR": "{FAALİYET KARI / ZARARI}+{E}-{F}-{G}",
    "DÖNEM KARI / ZARARI": "{OLAĞAN KAR / ZARAR}+{H}-{I}",
    "DÖNEM NET KARI / ZARARI": "{DÖNEM KARI / ZARARI}-{J}",
}


def _mizan(kod):
    return f'SUMIF({MZ}!$A:$A,"{kod}",{MZ}!$C:$C)'


def _bicim(c, tur, sayi=True, yuzde=False):
    if sayi:
        c.number_format = YUZDE if yuzde else SAYI
    if tur in RENK:
        c.font = Font(bold=True)
        c.fill = PatternFill("solid", fgColor=RENK[tur])


def _baglanti(kod, deger, ham, isaret):
    """Değer ham mizan bakiyesinin aynısıysa mizana bağlı formül, değilse None (değer yazılır)."""
    k = (kod or "").split("/")[0]
    if k in ham and deger is not None and abs(isaret * ham[k]["bakiye"] - deger) < 0.005:
        return ("=" if isaret > 0 else "=-") + _mizan(k)
    return None


def excel_formullu(r, hesaplar, yol, kontrol_metni=""):
    wb = Workbook()
    wb.remove(wb.active)
    ham = hesaplar

    # --- Kebir Mizan (kaynak) ---
    mz = wb.create_sheet("Kebir Mizan")
    mz.append(["Hesap Kodu", "Hesap Adı", "Bakiye (Borç − Alacak)"])
    for kod, v in sorted(ham.items()):
        mz.append([kod, v["ad"], v["bakiye"]])
        mz.cell(mz.max_row, 1).number_format = "@"
        mz.cell(mz.max_row, 3).number_format = SAYI
    _basliklar(mz, [12, 50, 20])

    # --- Envanter ve SMM ---
    ev = wb.create_sheet("Envanter ve SMM")
    ev.append(["Kod", "Satışların Maliyeti Tablosu", "Tutar"])
    smm_hucre = {}
    for tur, kod, ad, t in r["envanter"]:
        ev.append([kod, ad, None])
        c = ev.cell(ev.max_row, 3)
        f = _baglanti(kod, t, ham, 1) if tur == "kalem" and "mizan" in ad.lower() else None
        c.value = f or t
        _bicim(c, tur)
        _bicim(ev.cell(ev.max_row, 2), tur, sayi=False)
        if kod in ("620", "621", "622", "623"):
            smm_hucre[kod] = f"'Envanter ve SMM'!C{ev.max_row}"
    _basliklar(ev, [10, 70, 20])

    # --- Gelir Tablosu ---
    gt = wb.create_sheet("Gelir Tablosu")
    gt.append(["Kod", "Gelir Tablosu Kalemleri", "Tutar (₺)", "Dikey Oran"])
    hucre, bolum_satiri = {}, None
    satirlar = r["gelir_tablosu"]
    for i, (tur, kod, ad, t) in enumerate(satirlar):
        gt.append([kod, ad.strip() if tur != "kalem" else ad, None, None])
        n = gt.max_row
        c = gt.cell(n, 3)
        if tur == "bolum":
            son = n
            while son - n < len(satirlar) - i - 1 and satirlar[i + son - n + 1][0] == "kalem":
                son += 1
            c.value = f"=SUM(C{n + 1}:C{son})" if son > n else 0
            hucre[kod] = f"C{n}"
        elif tur == "ara":
            c.value = "=" + ARA_FORMUL[ad].format(**hucre) if ad in ARA_FORMUL else t
            hucre[ad] = f"C{n}"
        else:
            k = kod.split("/")[-1] if "/" in kod else kod
            isaret = -1 if kod[:1] == "6" and kod[:2] in ("60", "64", "67") else 1
            f = _baglanti(kod, t, ham, isaret)
            if f is None and k in smm_hucre and abs(t) >= 0.005:
                f = "=" + smm_hucre[k]
            c.value = f or t
        _bicim(c, tur)
        _bicim(gt.cell(n, 2), tur, sayi=False)
    net = hucre.get("NET SATIŞLAR")
    for n in range(2, gt.max_row + 1):
        if net:
            d = gt.cell(n, 4)
            d.value = f"=IF({net}=0,\"\",C{n}/{net})"
            d.number_format = YUZDE
    _basliklar(gt, [10, 55, 20, 12])

    # --- Detaylı Bilanço (aktif A:C, pasif E:G) ---
    bl = wb.create_sheet("Detaylı Bilanço")
    bl.append(["Kod", "AKTİF (VARLIKLAR)", "Tutar (₺)", "", "Kod", "PASİF (KAYNAKLAR)", "Tutar (₺)"])
    bh = {}

    def taraf(satirlar_, sut, isaret):
        k_, a_, t_ = sut
        siniflar, satir_no = [], 2
        grup_bas = sinif_bas = None
        gruplar_sinifta = []
        kayit = []  # (satır, tür)
        for tur, kod, ad, t in satirlar_:
            bl[f"{k_}{satir_no}"], bl[f"{a_}{satir_no}"] = kod, ad
            c = bl[f"{t_}{satir_no}"]
            if tur == "kalem":
                f = _baglanti(kod, t, ham, isaret)
                if kod == "590/591":
                    f = "='Gelir Tablosu'!" + gt_net
                c.value = f or t
            kayit.append((satir_no, tur, kod))
            _bicim(c, tur)
            _bicim(bl[f"{a_}{satir_no}"], tur, sayi=False)
            satir_no += 1
        # grup = altındaki kalemler, sınıf = altındaki gruplar, toplam = sınıflar
        for j, (n, tur, kod) in enumerate(kayit):
            if tur == "grup":
                son = n
                while j + son - n + 1 < len(kayit) and kayit[j + son - n + 1][1] == "kalem":
                    son += 1
                bl[f"{t_}{n}"] = f"=SUM({t_}{n + 1}:{t_}{son})" if son > n else 0
            elif tur == "sinif":
                gruplar = []
                for n2, tur2, _ in kayit[j + 1:]:
                    if tur2 in ("sinif", "toplam"):
                        break
                    if tur2 == "grup":
                        gruplar.append(f"{t_}{n2}")
                bl[f"{t_}{n}"] = "=" + ("+".join(gruplar) if gruplar else "0")
                siniflar.append(f"{t_}{n}")
                bh[f"sinif{kod}"] = f"{t_}{n}"
            elif tur == "grup" or tur == "kalem":
                pass
            if tur == "grup":
                bh[f"grup{kod}"] = f"{t_}{n}"
            if tur == "toplam":
                bl[f"{t_}{n}"] = "=" + "+".join(siniflar)
                bh[kod] = f"{t_}{n}"

    gt_net = hucre.get("DÖNEM NET KARI / ZARARI", "C1")
    taraf(r["aktif"], ("A", "B", "C"), 1)
    taraf(r["pasif"], ("E", "F", "G"), -1)
    son = bl.max_row + 2
    bl[f"B{son}"] = "KONTROL: AKTİF − PASİF (0 olmalı)"
    bl[f"C{son}"] = f"={bh['AKTİF']}-{bh['PASİF']}"
    bl[f"C{son}"].number_format = SAYI
    _basliklar(bl, [9, 45, 18, 3, 9, 45, 18])

    # --- FGK ---
    fg = wb.create_sheet("FGK Hesaplama")
    fg.append(["Adım", "Hesaplama Unsuru", "Tutar / Oran"])
    s3, s4, s5 = (f"'Detaylı Bilanço'!{bh.get(f'sinif{x}', 'C1')}" for x in "345")
    formul = {"1": f"={s3}", "2": f"={s4}", "3": "=C2+C3", "4": f"={s5}", "5": "=MAX(0,C4-C5)",
              "6": "=IF(C4>0,MIN(1,C6/C4),0)",
              "7": f'=SUMIF({MZ}!$A:$A,"66*",{MZ}!$C:$C)+SUMIF({MZ}!$A:$A,"78*",{MZ}!$C:$C)',
              "9": "=MAX(0,C8-C9)", "11": "=C10*C7*C11"}
    for n_, ad, t in r["fgk"]:
        fg.append([n_, ad, formul.get(n_, t)])
        c = fg.cell(fg.max_row, 3)
        _bicim(c, "ara" if n_ == "11" else "", yuzde=n_ in ("6", "10"))
    _basliklar(fg, [8, 55, 20])

    # --- Vergi ve Rasyolar ---
    vr = wb.create_sheet("Vergi ve Rasyolar")
    vr.append(["Kalem", "Tutar / Oran"])
    adres = {}
    for ad, t in r["vergi"]:
        vr.append([ad, t])
        adres[ad.split(" (")[0]] = f"B{vr.max_row}"
    a = lambda anahtar: next((v for k, v in adres.items() if k.startswith(anahtar)), None)
    vergi_satir = a("HESAPLANAN KURUMLAR VERGİSİ")
    oran = next((t for ad, t in r["vergi"] if ad.startswith("HESAPLANAN")), 0)
    matrah_t = next((t for ad, t in r["vergi"] if ad.startswith("MALİ KAR")), 0)
    vf = {a("950 Kanunen"): "=" + _mizan("950"), a("FGK Kanunen"): "='FGK Hesaplama'!C12",
          a("TOPLAM KKEG"): f"={a('950 Kanunen')}+{a('FGK Kanunen')}",
          a("DÖNEM KARI"): "='Gelir Tablosu'!" + hucre.get("DÖNEM KARI / ZARARI", "C1"),
          a("MALİ KAR"): (f"=MAX(0,{a('DÖNEM KARI')}+{a('TOPLAM KKEG')}-{a('İştirak')}-{a('Mahsup')}"
                          f"-{a('Ar-Ge İndirimi')}-{a('Bağış ve')}-{a('Tamamı')})"),
          vergi_satir: f"={a('MALİ KAR')}*{(oran / matrah_t) if matrah_t else 0}",
          a("ÖDENEN GEÇİCİ"): "=" + _mizan("193"),
          a("ÖDENECEK VERGİ"): f"={vergi_satir}-{a('ÖDENEN GEÇİCİ')}",
          a("VERGİ SONRASI"): f"={a('DÖNEM KARI')}-{vergi_satir}"}
    for hucre_, f in vf.items():
        if hucre_ and None not in (hucre_,):
            vr[hucre_] = f
    if matrah_t == 0 and vergi_satir:   # matrah 0 iken oran bulunamaz: vergi değer olarak kalsın
        vr[vergi_satir] = oran
    for n in range(2, vr.max_row + 1):
        ad = vr.cell(n, 1).value
        _bicim(vr.cell(n, 2), "ara" if any(x in ad for x in ("TOPLAM", "MATRAH", "ÖDENECEK")) else "")
    vr.append([])
    vr.append(["FİNANSAL RASYOLAR", None])
    _bicim(vr.cell(vr.max_row, 1), "bolum", sayi=False)
    B = lambda k: f"'Detaylı Bilanço'!{bh[k]}" if k in bh else "0"   # bilançoda olmayan sınıf/grup = 0
    gtc = lambda k: "'Gelir Tablosu'!" + hucre.get(k, "C1")
    rasyo_f = {"Cari Oran": f"{B('sinif1')}/{B('sinif3')}",
               "Asit-Test Oranı": f"({B('sinif1')}-{B('grup15')})/{B('sinif3')}",
               "Nakit Oranı": f"{B('grup10')}/{B('sinif3')}",
               "Finansal Kaldıraç (Yabancı Kaynak / Pasif)": f"({B('sinif3')}+{B('sinif4')})/{B('PASİF')}",
               "Öz Kaynak / Pasif": f"{B('sinif5')}/{B('PASİF')}",
               "Yabancı Kaynak / Öz Kaynak": f"({B('sinif3')}+{B('sinif4')})/{B('sinif5')}",
               "Aktif Devir Hızı": f"{gtc('NET SATIŞLAR')}/{B('AKTİF')}",
               "Öz Kaynak Kârlılığı (ROE)": f"{gtc('DÖNEM KARI / ZARARI')}/{B('sinif5')}",
               "Aktif Kârlılığı (ROA)": f"{gtc('DÖNEM KARI / ZARARI')}/{B('AKTİF')}"}
    for ad, v in r["rasyo"]:
        f = rasyo_f.get(ad)
        vr.append([ad, f'=IFERROR({f},"")' if f else v])
        vr.cell(vr.max_row, 2).number_format = "0.00"
    _basliklar(vr, [55, 22])

    if kontrol_metni:
        kt = wb.create_sheet("Kontrol")
        for i, s in enumerate(kontrol_metni.splitlines(), 1):
            kt.cell(i, 1, s)
        kt.column_dimensions["A"].width = 120
    wb.move_sheet("Kebir Mizan", offset=len(wb.sheetnames))
    wb.save(yol)


def _basliklar(ws, genislik):
    for j, g in enumerate(genislik, 1):
        ws.cell(1, j).font = Font(bold=True)
        ws.cell(1, j).alignment = Alignment(horizontal="center")
        ws.column_dimensions[chr(64 + j)].width = g
    ws.freeze_panes = "A2"


def rapor_html(r, baslik):
    """Yazıcı / PDF için tek HTML belge; her rapor yeni sayfada."""
    e = html.escape

    def tl(x):
        if x is None or isinstance(x, str):
            return e(x or "")
        return f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    def tablo(bas, satirlar):
        s = ["<table width='100%' cellspacing='0' cellpadding='3' style='border-collapse:collapse;font-size:8.5pt'>",
             "<tr>" + "".join(f"<th align='left' style='border-bottom:1px solid #000'>{e(b)}</th>" for b in bas) + "</tr>"]
        for tur, hucreler in satirlar:
            renk = {"sinif": "#dbe7f5", "bolum": "#dbe7f5", "grup": "#eef3f9", "ara": "#fff2cc", "toplam": "#c9e4c5"}.get(tur)
            stil = f" style='background:{renk};font-weight:bold'" if renk else ""
            s.append(f"<tr{stil}>" + "".join(
                f"<td align='right'>{tl(h)}</td>" if isinstance(h, (int, float)) and not isinstance(h, bool)
                else f"<td>{e(str(h or ''))}</td>" for h in hucreler) + "</tr>")
        return "\n".join(s + ["</table>"])

    ns = r["net_satis"]
    yuzde = lambda x: "" if x is None else f"%{x * 100:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    a, p = r["aktif"], r["pasif"]
    n = max(len(a), len(p))
    bos = ("", "", "", None)
    a = a[:-1] + [bos] * (n - len(a)) + a[-1:]
    p = p[:-1] + [bos] * (n - len(p)) + p[-1:]
    bolumler = [
        ("Satışların Maliyeti (Envanter ve SMM)", tablo(["Kod", "Kalem", "Tutar"],
            [(t if t != "kalem" else "", [k, ad, v]) for t, k, ad, v in r["envanter"]])),
        ("Gelir Tablosu", tablo(["Kod", "Kalem", "Tutar (₺)", "Dikey"],
            [(t, [k, ad, v, yuzde(v / ns) if ns and v is not None else ""]) for t, k, ad, v in r["gelir_tablosu"]])),
        ("Detaylı Bilanço", tablo(["Kod", "Aktif", "Tutar", "Kod", "Pasif", "Tutar"],
            [(x[0] or y[0], [x[1], x[2], x[3], y[1], y[2], y[3]]) for x, y in zip(a, p)])),
        ("Finansman Gider Kısıtlaması", tablo(["Adım", "Unsur", "Tutar / Oran"],
            [("ara" if k == "11" else "", [k, ad, yuzde(v) if k in ("6", "10") else v]) for k, ad, v in r["fgk"]])),
        ("Kurumlar Vergisi ve Rasyolar", tablo(["Kalem", "Tutar / Oran"],
            [("ara" if any(x in ad for x in ("TOPLAM", "MATRAH", "ÖDENECEK")) else "", [ad, v]) for ad, v in r["vergi"]]
            + [("bolum", ["FİNANSAL RASYOLAR", ""])]
            + [("", [ad, "" if v is None else f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")])
               for ad, v in r["rasyo"]])),
    ]
    tarih = time.strftime("%d.%m.%Y %H:%M")
    govde = []
    for i, (ad, t) in enumerate(bolumler):
        kir = " style='page-break-before:always'" if i else ""
        govde.append(f"<h3{kir}>{e(baslik)} — {e(ad)}</h3><p style='font-size:7.5pt;color:#555'>Başkan · {tarih}</p>{t}")
    return "<html><body style='font-family:Arial'>" + "\n".join(govde) + "</body></html>"
