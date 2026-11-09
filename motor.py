"""Kebir bakiyelerinden (borç−alacak) Tek Düzen'e uygun Bilanço, Gelir Tablosu, SMM, FGK ve vergi hesabı."""

GRUP = {  # 2 haneli grup adları
    "10": "HAZIR DEĞERLER", "11": "MENKUL KIYMETLER", "12": "TİCARİ ALACAKLAR", "13": "DİĞER ALACAKLAR",
    "15": "STOKLAR", "17": "YILLARA YAYGIN İNŞAAT VE ONARIM MALİYETLERİ",
    "18": "GELECEK AYLARA AİT GİDERLER VE GELİR TAHAKKUKLARI", "19": "DİĞER DÖNEN VARLIKLAR",
    "22": "TİCARİ ALACAKLAR", "23": "DİĞER ALACAKLAR", "24": "MALİ DURAN VARLIKLAR",
    "25": "MADDİ DURAN VARLIKLAR", "26": "MADDİ OLMAYAN DURAN VARLIKLAR", "27": "ÖZEL TÜKENMEYE TABİ VARLIKLAR",
    "28": "GELECEK YILLARA AİT GİDERLER VE GELİR TAHAKKUKLARI", "29": "DİĞER DURAN VARLIKLAR",
    "30": "MALİ BORÇLAR", "32": "TİCARİ BORÇLAR", "33": "DİĞER BORÇLAR", "34": "ALINAN AVANSLAR",
    "35": "YILLARA YAYGIN İNŞAAT VE ONARIM HAKEDİŞLERİ", "36": "ÖDENECEK VERGİ VE DİĞER YÜKÜMLÜLÜKLER",
    "37": "BORÇ VE GİDER KARŞILIKLARI", "38": "GELECEK AYLARA AİT GELİRLER VE GİDER TAHAKKUKLARI",
    "39": "DİĞER KISA VADELİ YABANCI KAYNAKLAR",
    "40": "MALİ BORÇLAR", "42": "TİCARİ BORÇLAR", "43": "DİĞER BORÇLAR", "44": "ALINAN AVANSLAR",
    "47": "BORÇ VE GİDER KARŞILIKLARI", "48": "GELECEK YILLARA AİT GELİRLER VE GİDER TAHAKKUKLARI",
    "49": "DİĞER UZUN VADELİ YABANCI KAYNAKLAR",
    "50": "ÖDENMİŞ SERMAYE", "52": "SERMAYE YEDEKLERİ", "54": "KAR YEDEKLERİ",
    "57": "GEÇMİŞ YILLAR KARLARI", "58": "GEÇMİŞ YILLAR ZARARLARI (-)", "59": "DÖNEM NET KARI / ZARARI",
}
SINIF = {"1": "DÖNEN VARLIKLAR", "2": "DURAN VARLIKLAR", "3": "KISA VADELİ YABANCI KAYNAKLAR",
         "4": "UZUN VADELİ YABANCI KAYNAKLAR", "5": "ÖZ KAYNAKLAR"}

# Gelir tablosu: (harf, başlık, hesap önekleri, işaret)  işaret -1: alacak bakiyeli gelir (−bakiye), +1: gider
# 7/A maliyet hesapları ilgili 6'lı hesaba aktarılır (yansıtma kullanılmışsa 7x0+7x1 zaten sıfırlanır).
GT_BOLUM = [
    ("A", "BRÜT SATIŞLAR", ["60"], -1),
    ("B", "SATIŞ İNDİRİMLERİ (-)", ["61"], 1),
    ("C", "SATIŞLARIN MALİYETİ (-)", ["62", "71", "72", "73", "74"], 1),
    ("D", "FAALİYET GİDERLERİ (-)", ["63", "75", "76", "77", "79"], 1),
    ("E", "DİĞER FAALİYETLERDEN OLAĞAN GELİR VE KARLAR", ["64"], -1),
    ("F", "DİĞER FAALİYETLERDEN OLAĞAN GİDER VE ZARARLAR (-)", ["65"], 1),
    ("G", "FİNANSMAN GİDERLERİ (-)", ["66", "78"], 1),
    ("H", "OLAĞANDIŞI GELİR VE KARLAR", ["67"], -1),
    ("I", "OLAĞANDIŞI GİDER VE ZARARLAR (-)", ["68"], 1),
    ("J", "DÖNEM KARI VERGİ VE DİĞ. YASAL YÜK. KARŞILIKLARI (-)", ["691"], 1),
]
YEDI_ALTI = {"71": "620", "72": "620", "73": "620", "74": "622", "75": "630", "76": "631", "77": "632",
             "78": "660", "79": "632"}


def bolum_kalemleri(hesaplar, onekler, isaret):
    kalem = []
    for kod in sorted(hesaplar):
        if any(kod.startswith(o) for o in onekler):
            tutar = isaret * hesaplar[kod]["bakiye"]
            if abs(tutar) < 0.005:
                continue
            etiket = f"{kod}/{YEDI_ALTI[kod[:2]]}" if kod[:2] in YEDI_ALTI else kod
            kalem.append((etiket, hesaplar[kod]["ad"], tutar))
    return kalem


STOK = {"150": "İLK MADDE VE MALZEME", "151": "YARI MAMULLER - ÜRETİM", "152": "MAMULLER",
        "153": "TİCARİ MALLAR"}
SMM_AD = {"620": "SATILAN MAMULLER MALİYETİ (-)", "621": "SATILAN TİCARİ MALLAR MALİYETİ (-)",
          "622": "SATILAN HİZMET MALİYETİ (-)", "623": "DİĞER SATIŞLARIN MALİYETİ (-)"}
YONTEMLER = ("oto", "envanter", "marj", "elle")


def _top(h, onek):
    return sum(v["bakiye"] for k, v in h.items() if k.startswith(onek))


def _yaz(h, kod, tutar, ad):
    h.setdefault(kod, {"ad": ad, "bakiye": 0.0})["bakiye"] = tutar


def envanter_smm(h, yontem="envanter", ds_stok=None, kar_marji=None, elle_miktar=None, elle_tutar=None,
                 ticari_satis=None):
    """150-153 stokları + 71x-74x üretim maliyetlerinden SMM (620/621/622/623) ve dönem sonu stokları.
    h yerinde değişir: stoklar dönem sonu değerine, 71x-74x sıfırlanıp 62x'e aktarılır.
    yontem: 'envanter' = dönem sonu fiili stoklar elle (girilmeyen stok mizan bakiyesinde kalır),
            'marj'     = SMM = net satış × (1 − brüt kâr oranı), satılabilir maliyet mizandan,
            'elle'     = depoda sayılan dönem sonu stok miktar + tutarı elle, SMM = satılabilir − stok
                         (brüt kâr oranı verilirse yalnız kontrol).
    kar_marji: brüt kâr / net satış (0,25 = %25) ya da {'150': oran, '153': oran} (gruba göre ayrı; ticari_satis
               = 153'ten yapılan net satış, verilmezse satılabilir maliyet payıyla bölünür). Dönüş: (tablo satırları, özet sözlüğü, uyarılar)."""
    uy, satir = [], []  # satır: (tür, kod, açıklama, tutar)
    ds_stok = {k: v for k, v in (ds_stok or {}).items() if v is not None}
    b = {s: h.get(s, {}).get("bakiye", 0.0) for s in STOK}
    t71, t72, t73, t74 = (_top(h, p) for p in ("71", "72", "73", "74"))
    m62 = {k: h.get(k, {}).get("bakiye", 0.0) for k in SMM_AD}
    net_satis = -_top(h, "60") - _top(h, "61")
    k = lambda kod, ad, t: satir.append(("kalem", kod, "  " + ad, t))

    if yontem == "envanter":
        if not ds_stok:
            uy.append("Dönem sonu fiili stoklar girilmedi: stoklar mizan bakiyesinde kaldı (sürekli envanter "
                      "varsayımı), SMM = mizandaki 62x + 71x-74x.")
        ds = {s: ds_stok.get(s, b[s]) for s in STOK}
        fark = {s: b[s] - ds[s] for s in STOK}
        for s in STOK:
            if fark[s] < -0.005:
                uy.append(f"{s} {STOK[s]}: fiili stok mizan bakiyesinden {fark[s] * -1:,.2f} büyük, SMM'yi azaltır.")
            if ds[s] < 0:
                uy.append(f"{s} {STOK[s]}: dönem sonu stok negatif.")
        dimm = fark["150"] + t71
        uretim = dimm + t72 + t73
        uretilen = uretim + fark["151"]
        s620 = uretilen + fark["152"] + m62["620"]
        s621 = fark["153"] + m62["621"]
        s622 = t74 + m62["622"]
        s623 = m62["623"]

        satir.append(("bolum", "A", "DİREKT İLK MADDE VE MALZEME GİDERLERİ", dimm))
        k("150", "Dönem başı stok + dönem içi alışlar (150 mizan bakiyesi)", b["150"])
        k("150", "Dönem sonu ilk madde ve malzeme stoku (-)", -ds["150"])
        k("710", "Mizandaki direkt ilk madde ve malzeme giderleri (71x net)", t71)
        satir.append(("bolum", "B", "DİREKT İŞÇİLİK GİDERLERİ (72x)", t72))
        satir.append(("bolum", "C", "GENEL ÜRETİM GİDERLERİ (73x)", t73))
        satir.append(("ara", "D", "DÖNEM ÜRETİM MALİYETİ (A+B+C)", uretim))
        satir.append(("bolum", "E", "YARI MAMUL STOK DEĞİŞİMİ", fark["151"]))
        k("151", "Dönem başı yarı mamul + girişler (151 mizan bakiyesi)", b["151"])
        k("151", "Dönem sonu yarı mamul stoku (-)", -ds["151"])
        satir.append(("ara", "F", "ÜRETİLEN MAMUL MALİYETİ (D+E)", uretilen))
        satir.append(("bolum", "G", "MAMUL STOK DEĞİŞİMİ", fark["152"]))
        k("152", "Dönem başı mamul + girişler (152 mizan bakiyesi)", b["152"])
        k("152", "Dönem sonu mamul stoku (-)", -ds["152"])
        if abs(m62["620"]) >= 0.005:
            k("620", "Mizanda kayıtlı satılan mamul maliyeti", m62["620"])
        satir.append(("ara", "620", "SATILAN MAMULLER MALİYETİ (F+G)", s620))
        satir.append(("bolum", "H", "TİCARİ MAL STOK DEĞİŞİMİ", fark["153"]))
        k("153", "Dönem başı stok + dönem içi net alışlar (153 mizan bakiyesi)", b["153"])
        k("153", "Dönem sonu ticari mal stoku (-)", -ds["153"])
        if abs(m62["621"]) >= 0.005:
            k("621", "Mizanda kayıtlı satılan ticari mal maliyeti", m62["621"])
        satir.append(("ara", "621", "SATILAN TİCARİ MALLAR MALİYETİ", s621))
        satir.append(("bolum", "I", "HİZMET ÜRETİM MALİYETİ (74x)", t74))
        if abs(m62["622"]) >= 0.005:
            k("622", "Mizanda kayıtlı satılan hizmet maliyeti", m62["622"])
        satir.append(("ara", "622", "SATILAN HİZMET MALİYETİ", s622))
        if abs(s623) >= 0.005:
            satir.append(("ara", "623", "DİĞER SATIŞLARIN MALİYETİ", s623))
        smm = {"620": s620, "621": s621, "622": s622, "623": s623}
        ozet_ek = {}
    elif yontem == "marj" and isinstance(kar_marji, dict):
        # 08.11: 150 grubu (150-152 + üretim/hizmet maliyeti → 620/622) ve 153 (ticari mal → 621) için AYRI
        # brüt kâr oranı. Satışın gruplara bölünüşü: ticari_satis girildiyse o, yoksa satılabilir maliyet oranı.
        maliyet = {"uretim": b["150"] + b["151"] + b["152"] + t71 + t72 + t73 + t74 + m62["620"] + m62["622"] + m62["623"],
                   "ticari": b["153"] + m62["621"]}
        oran = {"uretim": kar_marji.get("150"), "ticari": kar_marji.get("153")}
        # 08.11 (Kenan Bey): aynı satırda dönem sonu stok da girilebilir — stok doluysa stoktan, boşsa orandan.
        # 150 grubunun stoku = girilen 150 + 151/152 mizan bakiyeleri.
        stok = {"uretim": None if ds_stok.get("150") is None else ds_stok["150"] + b["151"] + b["152"],
                "ticari": ds_stok.get("153")}
        aktif = [g for g in maliyet if maliyet[g] > 0.005]
        for g in aktif:
            if oran[g] is None and stok[g] is None:
                raise ValueError(("150 grubu" if g == "uretim" else "153 ticari mal") +
                                 " için brüt kâr oranı ya da dönem sonu stok girilmedi.")
        if ticari_satis is not None:
            satis = {"ticari": ticari_satis, "uretim": net_satis - ticari_satis}
        elif len(aktif) == 1:
            satis = {g: (net_satis if g == aktif[0] else 0.0) for g in maliyet}
        else:
            pay = maliyet["ticari"] / (maliyet["ticari"] + maliyet["uretim"]) if aktif else 0.0
            satis = {"ticari": net_satis * pay, "uretim": net_satis * (1 - pay)}
            if any(stok[g] is None for g in aktif):   # bölüşüm yalnız oranla hesaplanan grubu etkiler
                uy.append(f"Ticari mal satış tutarı girilmedi: net satışın %{pay * 100:.1f}'i (satılabilir maliyet "
                          "payı) 153'e, kalanı 150 grubuna sayıldı. Gerçek ticari mal satışını alana yazın.")
        g_smm = {g: (maliyet[g] - stok[g]) if stok[g] is not None else satis[g] * (1 - (oran[g] or 0.0)) for g in maliyet}
        g_ds = {g: maliyet[g] - g_smm[g] for g in maliyet}
        for g in maliyet:
            if g_ds[g] < -0.005:
                uy.append(("150 grubu" if g == "uretim" else "153 ticari mal") + f": SMM ({g_smm[g]:,.2f}) satılabilir "
                          f"maliyeti ({maliyet[g]:,.2f}) aşıyor, dönem sonu stok negatif; oranı kontrol edin.")
        agirlik = {s: max(0.0, b[s]) for s in ("150", "151", "152")}
        if not sum(agirlik.values()):
            agirlik["152"] = 1.0
        ds = {s: g_ds["uretim"] * agirlik[s] / sum(agirlik.values()) for s in agirlik}
        if stok["uretim"] is not None:   # girilen 150, 151/152 mizanda kalır
            ds = {"150": ds_stok["150"], "151": b["151"], "152": b["152"]}
        ds["153"] = g_ds["ticari"]
        hizmet_pay = (t74 + m62["622"]) / maliyet["uretim"] if maliyet["uretim"] else 0.0
        smm = {"620": g_smm["uretim"] * (1 - hizmet_pay), "621": g_smm["ticari"],
               "622": g_smm["uretim"] * hizmet_pay, "623": 0.0}
        toplam_smm = g_smm["uretim"] + g_smm["ticari"]
        for g, harf, ad, stoklar in (("uretim", "A", "150 GRUBU (İLK MADDE, YARI MAMUL, MAMUL + ÜRETİM)", ("150", "151", "152")),
                                     ("ticari", "B", "153 TİCARİ MALLAR", ("153",))):
            if g not in aktif and abs(satis[g]) < 0.005:
                continue
            satir.append(("bolum", harf, ad, None))
            for s in stoklar:
                if abs(b[s]) >= 0.005:
                    k(s, f"{STOK[s]} (mizan bakiyesi)", b[s])
            if g == "uretim":
                for kod, ad_, t in (("710", "Direkt ilk madde ve malzeme (71x)", t71), ("720", "Direkt işçilik (72x)", t72),
                                    ("730", "Genel üretim giderleri (73x)", t73), ("740", "Hizmet üretim maliyeti (74x)", t74)):
                    if abs(t) >= 0.005:
                        k(kod, ad_, t)
            for kod in (("620", "622", "623") if g == "uretim" else ("621",)):
                if abs(m62[kod]) >= 0.005:
                    k(kod, "Mizanda kayıtlı " + SMM_AD[kod][:-4].lower(), m62[kod])
            satir.append(("ara", harf + "1", "SATILABİLİR MALİYET", maliyet[g]))
            if stok[g] is not None:
                k("150" if g == "uretim" else "153", "Dönem sonu stok (girilen" + (" 150 + 151/152 mizan)" if g == "uretim" else ")"), -stok[g])
                satir.append(("ara", "SMM", "SATIŞLARIN MALİYETİ = SATILABİLİR − DÖNEM SONU STOK", g_smm[g]))
            else:
                k("", "Bu gruba düşen net satış", satis[g])
                k("", f"Brüt kâr oranı %{(oran[g] or 0) * 100:g}", None)
                satir.append(("ara", "SMM", f"SATIŞLARIN MALİYETİ = SATIŞ × (1 − %{(oran[g] or 0) * 100:g})", g_smm[g]))
            satir.append(("ara", "DS", "DÖNEM SONU STOK (SATILABİLİR − SMM)", g_ds[g]))
        for kod in ("620", "621", "622"):
            if abs(smm[kod]) >= 0.005:
                k(kod, SMM_AD[kod][:-4], smm[kod])
        ozet_ek = {"satilabilir": sum(maliyet.values()), "grup_satis": satis}
    else:
        # 09.11 (Kenan Bey): 'elle' = depoda sayılan DÖNEM SONU stok (ör. 30.09'da satışa hazır stok) miktar + tutarı.
        # SMM = satılabilir maliyet (mizan stokları + 71x-74x + kayıtlı 62x) − sayılan stok; oran yalnız kontrol.
        if yontem == "elle" and elle_tutar is None:
            raise ValueError("Dönem sonu stok tutarı girilmedi.")
        if kar_marji is None and yontem != "elle":
            raise ValueError("Brüt kâr oranı girilmedi.")
        stok_baz, kayitli62 = sum(b.values()), sum(m62.values())
        uretim = t71 + t72 + t73
        satilabilir = stok_baz + uretim + t74 + kayitli62
        toplam_smm = satilabilir - elle_tutar if yontem == "elle" else net_satis * (1 - kar_marji)
        ds_top = satilabilir - toplam_smm
        if yontem == "elle" and toplam_smm < -0.005:
            uy.append(f"Girilen dönem sonu stok ({elle_tutar:,.2f}) satılabilir mal maliyetini ({satilabilir:,.2f}) "
                      "aşıyor: SMM negatif çıktı. Stok tutarını ya da mizandaki alışları kontrol edin.")
        if ds_top < -0.005:
            uy.append(f"Brüt kâr oranıyla bulunan SMM ({toplam_smm:,.2f}) satılabilir mal maliyetini "
                      f"({satilabilir:,.2f}) aşıyor: dönem sonu stok negatif çıktı, oranı kontrol edin.")
        # dönem sonu stok, mizandaki stok hesaplarına bakiyeleri oranında dağıtılır
        agirlik = {s: max(0.0, b[s]) for s in STOK}
        if not sum(agirlik.values()):
            agirlik["152" if uretim + t74 else "153"] = 1.0
        ag_top = sum(agirlik.values())
        ds = {s: ds_top * agirlik[s] / ag_top for s in STOK}
        # SMM, maliyet kaynağına göre 620 / 621 / 622'ye oranla bölünür
        ticari = stok_baz * agirlik["153"] / ag_top + m62["621"]
        hizmet = t74 + m62["622"]
        oran = (lambda x: x / satilabilir) if satilabilir else (lambda x: 0.0)
        s621, s622 = toplam_smm * oran(ticari), toplam_smm * oran(hizmet)
        smm = {"620": toplam_smm - s621 - s622, "621": s621, "622": s622, "623": 0.0}

        satir.append(("bolum", "A", "SATILABİLİR MAL MALİYETİ", satilabilir))
        for s in STOK:
            if abs(b[s]) >= 0.005:
                k(s, f"{STOK[s]} (mizan bakiyesi)", b[s])
        for kod, t in m62.items():
            if abs(t) >= 0.005:
                k(kod, "Mizanda kayıtlı " + SMM_AD[kod][:-4].lower(), t)
        for kod, ad, t in (("710", "Direkt ilk madde ve malzeme giderleri (71x)", t71),
                           ("720", "Direkt işçilik giderleri (72x)", t72),
                           ("730", "Genel üretim giderleri (73x)", t73),
                           ("740", "Hizmet üretim maliyeti (74x)", t74)):
            if abs(t) >= 0.005:
                k(kod, ad, t)
        satir.append(("bolum", "B", "NET SATIŞLAR", net_satis))
        if yontem == "elle":
            k("STOK", "Depoda sayılan dönem sonu stok (elle) (-)", -elle_tutar)
            satir.append(("ara", "SMM", "SATIŞLARIN MALİYETİ = A − DÖNEM SONU STOK", toplam_smm))
        else:
            satir.append(("ara", "SMM", f"SATIŞLARIN MALİYETİ = NET SATIŞ × (1 − %{kar_marji * 100:g})", toplam_smm))
        for kod in ("620", "621", "622"):
            if abs(smm[kod]) >= 0.005:
                k(kod, SMM_AD[kod][:-4], smm[kod])
        satir.append(("ara", "DS", "DÖNEM SONU STOK (A − SMM)", ds_top))
        for s in STOK:
            if abs(ds[s]) >= 0.005:
                k(s, STOK[s], ds[s])
        ozet_ek = {"satilabilir": satilabilir}
        if yontem == "elle":
            if elle_miktar:
                birim = elle_tutar / elle_miktar
                satir.append(("bolum", "MİKTAR", "DÖNEM SONU STOK MİKTARI", None))
                k("", "Depoda sayılan miktar", elle_miktar)
                k("", "Birim maliyet (stok tutarı / miktar)", birim)
                ozet_ek.update(birim=birim, ds_miktar=elle_miktar)
            if kar_marji is not None:   # oran girildiyse yalnız kontrol: oranla beklenen SMM ile karşılaştır
                beklenen = net_satis * (1 - kar_marji)
                satir.append(("bolum", "KONTROL", f"BRÜT KÂR ORANI KONTROLÜ (%{kar_marji * 100:g})", None))
                k("", "Oranla beklenen SMM = net satış × (1 − oran)", beklenen)
                k("", "Sayımla bulunan SMM − beklenen", toplam_smm - beklenen)
                if net_satis and abs(toplam_smm - beklenen) > 0.01 * abs(net_satis):
                    gercek = (net_satis - toplam_smm) / net_satis * 100
                    uy.append(f"Sayılan stokla brüt kâr oranı %{gercek:.1f} çıktı, girilen oran %{kar_marji * 100:g}: "
                              f"fark {toplam_smm - beklenen:,.2f}. Sayımı ya da oranı kontrol edin.")

    # h'ye uygula: stoklar dönem sonuna, 71x-74x 62x'e aktarıldı
    for s in STOK:
        if s in h or abs(ds[s]) >= 0.005:
            _yaz(h, s, ds[s], STOK[s])
    for kod in [x for x in h if x[:2] in ("71", "72", "73", "74")]:
        h[kod]["bakiye"] = 0.0
    for kod, t in smm.items():
        if kod in h or abs(t) >= 0.005:
            _yaz(h, kod, t, SMM_AD[kod])
    toplam = sum(smm.values())
    satir.append(("toplam", "62", "SATIŞLARIN MALİYETİ TOPLAMI (SMM)", toplam))
    brut = net_satis - toplam
    satir.append(("ara", "", "BRÜT SATIŞ KÂRI", brut))
    ozet = {"smm": toplam, "net_satis": net_satis, "brut_kar": brut,
            "brut_oran": brut / net_satis if net_satis else None, "donem_sonu_stok": ds, **ozet_ek}
    return satir, ozet, uy


def envanter_analiz(h):
    """Mizandan her stok hesabının izlenme biçimini tanır (ERP'den bağımsız, yalnız hesap planı mantığıyla).
    sürekli : çıkış kaydı defterde var (62x / 710 kayıtlı) -> mizan bakiyesi = defterdeki dönem sonu stok
    aralıklı: çıkış hiç kaydedilmemiş, bakiye = dönem başı + girişler -> dönem sonu sayım (veya oran) gerekir
    Dönüş: {'hesap': {kod: (sistem, gerekçe)}, 'gerekli': [kod], 'metin': [satır]}"""
    bak = lambda k: h.get(k, {}).get("bakiye", 0.0)
    hareket = lambda k: (h.get(k, {}).get("borc"), h.get(k, {}).get("alacak"))
    var = lambda t: abs(t) >= 0.005
    satis = -_top(h, "60") - _top(h, "61")
    t71, t72, t73, t74, t79 = (_top(h, p) for p in ("71", "72", "73", "74", "79"))
    s620, s621, s622 = bak("620"), bak("621"), bak("622")
    yans = [k for k in ("711", "721", "731", "741") if var(bak(k))]
    sonuc, metin = {}, []

    def cikis_orani(k):
        b, a = hareket(k)
        return a / b if b and a is not None and b > 0 else None

    def karar(kod, kayitli, kayit_ad):
        b = bak(kod)
        if not var(b) and not kayitli:
            return None
        oran = cikis_orani(kod)
        oran_m = "" if oran is None else f", alacak/borç %{oran * 100:.0f}"
        if kayitli:
            return "sürekli", f"{kayit_ad} kayıtlı, bakiye defterdeki dönem sonu stok{oran_m}"
        if oran is not None and oran >= 0.10:
            return "belirsiz", (f"çıkış kaydı var (alacak/borç %{oran * 100:.0f}) ama {kayit_ad} yok: çıkış "
                                "başka hesaba gitmiş olabilir, dönem sonu sayımı girin")
        return "aralıklı", f"{kayit_ad} kaydı yok, bakiye dönem başı + girişler{oran_m}: dönem sonu sayımı gerekir"

    sonuc["153"] = karar("153", var(s621), "621 satılan ticari mal maliyeti")
    uretim_kayitli = var(s620)
    sonuc["152"] = karar("152", uretim_kayitli, "620 satılan mamul maliyeti")
    sonuc["151"] = karar("151", uretim_kayitli or (var(bak("152")) and sonuc["152"][0] == "sürekli"),
                         "620 / mamul aktarımı")
    o150 = cikis_orani("150")  # 710 brüt bakiyesi: 711 ile yansıtılmış olsa da tüketim kaydını gösterir
    sonuc["150"] = karar("150", uretim_kayitli or (var(bak("710")) and (o150 is None or o150 >= 0.10)),
                         "710 malzeme tüketimi")
    sonuc = {k: v for k, v in sonuc.items() if v}
    gerekli = [k for k, (sistem, _) in sonuc.items() if sistem != "sürekli"]

    for k, (sistem, neden) in sorted(sonuc.items()):
        metin.append(f"{k} {STOK[k]}: {sistem.upper()} envanter — {neden}")
    if var(t71 + t72 + t73):
        metin.append(f"Üretim maliyeti 71x-73x yansıtılmamış ({t71 + t72 + t73:,.2f}): SMM'ye 620 yoluyla eklenir.")
    elif yans:
        metin.append("Üretim maliyetleri " + "/".join(yans) + " ile yansıtılmış: 151/152 bakiyelerinde.")
    if var(t74):
        metin.append(f"74x hizmet üretim maliyeti {t74:,.2f}: 622'ye aktarılır.")
    if var(t79):
        metin.append(f"7/B: 79x net bakiye {t79:,.2f} yansıtılmamış, faaliyet gideri sayıldı (799 varsa SMM'dir).")
    elif any(k[:2] == "79" for k in h):
        metin.append("7/B: 79x hesapları 798 ile yansıtılmış.")
    if var(satis) and not sonuc and not var(s620 + s621 + s622) and not var(t71 + t72 + t73 + t74):
        metin.append("Satış var ama stok, üretim ve SMM hesabı yok: SMM sıfır çıkar (hizmet / komisyon işi?).")
    if not gerekli:
        metin.append("SONUÇ: SMM mizandan otomatik hesaplandı, giriş gerekmez (sayım farkı varsa dönem sonu "
                     "stoku girin).")
    else:
        metin.append("SONUÇ: " + ", ".join(gerekli) + " için dönem sonu sayım stoku girin YA DA brüt kâr oranı "
                     "yazın.")
    return {"hesap": sonuc, "gerekli": gerekli, "metin": metin}


def hesapla(hesaplar, stok=None, fgk_istisna=0.0, fgk_oran=0.10, vergi_orani=0.25, yontem="envanter",
            ds_stok=None, kar_marji=None, elle_miktar=None, elle_tutar=None, istirak=None, gecmis_zarar=0.0,
            arge=0.0, bagis=0.0, bagis_tam=0.0, ticari_satis=None):
    """hesaplar: {kebir: {'ad','bakiye'}} (bakiye = borç − alacak). stok: eski kullanım, 153 dönem sonu
    fiili stoğu (ds_stok={'153': stok} ile aynı). SMM yöntemleri için envanter_smm'e bakın.
    Dönüş: tablolar ve kontrol sonuçlarını içeren sözlük."""
    h = {k: dict(v) for k, v in hesaplar.items()}
    uyarilar = []

    # --- ENVANTER VE SMM ---
    ds_stok = {k: v for k, v in (ds_stok or {}).items() if v is not None}
    if stok is not None:
        ds_stok.setdefault("153", stok)
    analiz = envanter_analiz(h)
    if yontem == "oto":  # mizan sürekli envanterse giriş istemez; aralıklıysa sayım, o da yoksa oran
        eksik = [k for k in analiz["gerekli"] if k not in ds_stok]
        if not eksik:
            yontem = "envanter"
            if analiz["gerekli"]:
                analiz["metin"][-1] = ("SONUÇ: " + ", ".join(analiz["gerekli"]) + " sayım stoku girildi, SMM "
                                       "stok farkı + üretim maliyetleriyle hesaplandı.")
        elif kar_marji is not None:
            yontem = "marj"
            analiz["metin"][-1] = "SONUÇ: sayım stoku eksik, SMM brüt kâr oranından hesaplandı."
        else:
            yontem = "envanter"
            uyarilar.append("SMM EKSİK: " + ", ".join(eksik) + " aralıklı envanterle izleniyor, dönem sonu stoku "
                            "girilmedi; bu stoklar satılmamış sayıldı. Sayım stokunu ya da brüt kâr oranını girin.")
        analiz["eksik"] = eksik
    analiz["secilen"] = yontem
    envanter, smm_ozet, uy = envanter_smm(h, yontem, ds_stok, kar_marji, elle_miktar, elle_tutar, ticari_satis)
    uyarilar += uy

    # --- GELİR TABLOSU ---
    gt = {}
    for harf, baslik, onek, isaret in GT_BOLUM:
        kalem = bolum_kalemleri(h, onek, isaret)
        gt[harf] = (baslik, sum(t for *_, t in kalem), kalem)
    t = {harf: gt[harf][1] for harf in gt}
    ara = {
        "NET SATIŞLAR": t["A"] - t["B"],
    }
    ara["BRÜT SATIŞ KARI / ZARARI"] = ara["NET SATIŞLAR"] - t["C"]
    ara["FAALİYET KARI / ZARARI"] = ara["BRÜT SATIŞ KARI / ZARARI"] - t["D"]
    ara["OLAĞAN KAR / ZARAR"] = ara["FAALİYET KARI / ZARARI"] + t["E"] - t["F"] - t["G"]
    ara["DÖNEM KARI / ZARARI"] = ara["OLAĞAN KAR / ZARAR"] + t["H"] - t["I"]
    ara["DÖNEM NET KARI / ZARARI"] = ara["DÖNEM KARI / ZARARI"] - t["J"]
    sira = [("A",), ("B",), ("NET SATIŞLAR",), ("C",), ("BRÜT SATIŞ KARI / ZARARI",), ("D",),
            ("FAALİYET KARI / ZARARI",), ("E",), ("F",), ("G",), ("OLAĞAN KAR / ZARAR",), ("H",), ("I",),
            ("DÖNEM KARI / ZARARI",), ("J",), ("DÖNEM NET KARI / ZARARI",)]
    net_satis = ara["NET SATIŞLAR"]
    gelir_tablosu = []  # (tür, kod, ad, tutar)  tür: bolum/kalem/ara
    for (anahtar,) in sira:
        if anahtar in gt:
            baslik, tutar, kalem = gt[anahtar]
            gelir_tablosu.append(("bolum", anahtar, baslik, tutar))
            gelir_tablosu += [("kalem", k, "  " + ad, tt) for k, ad, tt in kalem]
        else:
            gelir_tablosu.append(("ara", "", anahtar, ara[anahtar]))
    donem_kari = ara["DÖNEM KARI / ZARARI"]
    # Bilançoya vergi karşılığı (691) düşülmüş NET kâr gider: 691 kayıtlıysa karşılığı 370'te pasifte durur
    net_kar = ara["DÖNEM NET KARI / ZARARI"]
    gelir_hesap = [k for k in h if k[0] == "6" and k[:2] != "69"]
    if "690" in h and abs(h["690"]["bakiye"]) >= 0.005 and \
            all(abs(h[k]["bakiye"]) < 0.005 for k in gelir_hesap):
        uyarilar.append("Mizan KAPANIŞ kayıtlarından sonra alınmış (6'lı hesaplar 690'a devredilmiş): gelir "
                        "tablosu boş çıkar. Kapanış öncesi mizanı yükleyin.")

    # --- BİLANÇO --- (59'a cari dönem kârı eklenir; 69x kapanış hesapları gelir tablosunda sayılmaz)
    def taraf(siniflar, isaret):
        satirlar, toplamlar = [], {}
        for s in siniflar:
            s_satir, s_toplam = [], 0.0
            for g in sorted({k[:2] for k in h if k[0] == s} | ({"59"} if s == "5" else set())):
                kalem = [(k, h[k]["ad"], isaret * h[k]["bakiye"]) for k in sorted(h)
                         if k[:2] == g and abs(h[k]["bakiye"]) >= 0.005]
                if g == "59":
                    kalem.append(("590/591", "Cari Dönem Net Kârı / Zararı (Gelir Tablosundan)", net_kar))
                if not kalem:
                    continue
                g_toplam = sum(x[2] for x in kalem)
                s_satir.append(("grup", g, GRUP.get(g, f"{g} GRUBU"), g_toplam))
                s_satir += [("kalem", k, "  " + ad, tt) for k, ad, tt in kalem]
                s_toplam += g_toplam
            satirlar.append(("sinif", s, SINIF[s], s_toplam))
            satirlar += s_satir
            toplamlar[s] = s_toplam
        return satirlar, toplamlar

    aktif, at = taraf("12", 1)
    pasif, pt = taraf("345", -1)
    aktif_top, pasif_top = at["1"] + at["2"], pt["3"] + pt["4"] + pt["5"]
    aktif.append(("toplam", "AKTİF", "AKTİF (VARLIKLAR) TOPLAMI", aktif_top))
    pasif.append(("toplam", "PASİF", "PASİF (KAYNAKLAR) TOPLAMI", pasif_top))
    fark = round(aktif_top - pasif_top, 2)
    if fark:
        uyarilar.append(f"BİLANÇO DENGESİZ: aktif − pasif = {fark:,.2f}")
    sinifsiz = [k for k in h if abs(h[k]["bakiye"]) >= 0.005 and
                (k[0] in "08" or k[:2] == "70" or (k[:2] == "69" and k != "691"))]
    if sinifsiz:
        uyarilar.append("Hesaplamaya alınmayan hesaplar: " + ", ".join(sorted(sinifsiz)))

    # --- FGK (KVK 11/1-i) ---
    yabanci = pt["3"] + pt["4"]
    oz = pt["5"]
    asan = max(0.0, yabanci - oz)
    asan_oran = min(1.0, asan / yabanci) if yabanci > 0 else 0.0
    fin_gider = sum(h[k]["bakiye"] for k in h if k[:2] in ("66", "78"))
    kisita_tabi = max(0.0, fin_gider - fgk_istisna)
    fgk_kkeg = kisita_tabi * asan_oran * fgk_oran
    fgk = [("1", "Kısa Vadeli Yabancı Kaynaklar (3xx)", pt["3"]),
           ("2", "Uzun Vadeli Yabancı Kaynaklar (4xx)", pt["4"]),
           ("3", "TOPLAM YABANCI KAYNAKLAR", yabanci),
           ("4", "TOPLAM ÖZ KAYNAKLAR (dönem kârı dahil)", oz),
           ("5", "Yabancı Kaynakların Öz Kaynakları Aşan Kısmı", asan),
           ("6", "Aşan Kısım Oranı", asan_oran),
           ("7", "Toplam Finansman Giderleri (66x + 78x)", fin_gider),
           ("8", "Yatırım Maliyetine Eklenen Finansman Giderleri (-)", fgk_istisna),
           ("9", "Kısıtlamaya Tabi Net Finansman Gideri", kisita_tabi),
           ("10", "Kısıtlama Oranı", fgk_oran),
           ("11", "FGK KANUNEN KABUL EDİLMEYEN GİDER", fgk_kkeg)]

    # --- VERGİ ---
    kkeg_950 = h.get("950", {}).get("bakiye", 0.0)
    kkeg = kkeg_950 + fgk_kkeg
    # Beyanname sırası: kâr + KKEG − zarar olsa dahi indirilecek istisna (iştirak, KVK 5/1-a)
    #                   − geçmiş yıl zararı (yalnız pozitif kazançtan, en çok kazanç kadar; KVK 9)
    if istirak is None:  # girilmediyse mizandaki 640 + 641 temettü gelirleri
        istirak = max(0.0, -(h.get("640", {}).get("bakiye", 0.0) + h.get("641", {}).get("bakiye", 0.0)))
        if istirak >= 0.005:
            uyarilar.append(f"İştirak kazancı istisnası mizandaki 640/641'den alındı ({istirak:,.2f}): yurt dışı "
                            "iştirak ve kâr payı şartlarını kontrol edin, gerekirse alana tutarı yazın.")
    istirak = max(0.0, istirak)
    gecmis_zarar = max(0.0, gecmis_zarar or 0.0)
    istisna_sonrasi = donem_kari + kkeg - istirak
    mahsup = min(gecmis_zarar, max(0.0, istisna_sonrasi))
    matrah = istisna_sonrasi - mahsup
    devreden = gecmis_zarar - mahsup + max(0.0, -matrah)
    # Kazanç olması halinde indirilecekler (zarar mahsubundan sonra, kalan kazançla sınırlı):
    # 09.11 (Kenan Bey): SIRA önce bağış, sonra Ar-Ge.
    # Bağış (KVK 10/1-c): zarar mahsubu sonrası kazancın %5'iyle sınırlı, aşan kısım kaybolur
    # Tamamı indirilen bağışlar (KVK 10/1-ç, ı, j vb.): kalan kazançla sınırlı, devretmez
    # Ar-Ge indirimi (5746 / KVK 10/1-a): bağışlardan sonra kalan kazançtan; yetmeyen kısım sonraki yıla devreder
    arge, bagis, bagis_tam = (max(0.0, x or 0.0) for x in (arge, bagis, bagis_tam))
    kazanc = max(0.0, matrah)
    bagis_sinir = 0.05 * kazanc
    bagis_ind = min(bagis, bagis_sinir)
    kazanc -= bagis_ind
    tam_ind = min(bagis_tam, kazanc)
    kazanc -= tam_ind
    arge_ind = min(arge, kazanc)
    kazanc -= arge_ind
    if matrah > 0:
        matrah = kazanc
    arge_devreden = arge - arge_ind
    if arge_devreden >= 0.005:
        uyarilar.append(f"Ar-Ge indiriminin {arge_devreden:,.2f} kısmı kazanç yetmediği için indirilemedi, "
                        "sonraki yıla devreder (yeniden değerleme oranıyla artırılır).")
    if bagis - bagis_ind >= 0.005:
        uyarilar.append(f"Bağışın {bagis - bagis_ind:,.2f} kısmı %5 sınırını ({bagis_sinir:,.2f}) aştığı için indirilemedi, devretmez (KKEG olarak kalır).")
    if bagis_tam - tam_ind >= 0.005:
        uyarilar.append(f"Tamamı indirilen bağışın {bagis_tam - tam_ind:,.2f} kısmı kalan kazancı aştı, "
                        "indirilemedi ve devretmez.")
    if gecmis_zarar > mahsup + 0.005:
        uyarilar.append(f"Geçmiş yıl zararının {gecmis_zarar - mahsup:,.2f} kısmı bu yıl mahsup edilemedi, "
                        "sonraki yıla devreder (5 yıl sınırını kontrol edin).")
    b580 = h.get("580", {}).get("bakiye", 0.0)
    if b580 >= 0.005 and not gecmis_zarar:
        uyarilar.append(f"Mizanda 580 geçmiş yıllar zararı {b580:,.2f} var: mali zarar tutarını (beyannamedeki "
                        "devreden zarar, son 5 yıl) Geçmiş yıl zararı alanına yazın.")
    vergi = max(0.0, matrah) * vergi_orani
    pesin = h.get("193", {}).get("bakiye", 0.0)
    if abs(t["J"]) >= 0.005 and abs(t["J"] - vergi) >= 1:
        uyarilar.append(f"Mizanda 691 vergi karşılığı {t['J']:,.2f}, hesaplanan kurumlar vergisi {vergi:,.2f}: "
                        "fark kadar 691/370 kaydı düzeltilmeli.")
    if abs(h.get("656", {}).get("bakiye", 0.0)) >= 0.005:
        uyarilar.append(f"656 Kambiyo Zararları {h['656']['bakiye']:,.2f}: yabancı kaynaklara (kredi, borç) ait "
                        "kur farkı zararları finansman gideri kısıtlamasına girer, otomatik eklenmedi. "
                        "O kısmı ayırıp FGK'ya ekleyin.")
    if "79" in {k[:2] for k in h if abs(h[k]["bakiye"]) >= 0.005}:
        uyarilar.append("79x (7/B) hesapları faaliyet gideri sayıldı: üretim maliyetine giden kısım (799) "
                        "varsa SMM'ye aktarılmalı.")
    vergi_tab = [("950 Kanunen Kabul Edilmeyen Giderler", kkeg_950),
                 ("FGK Kanunen Kabul Edilmeyen Gider", fgk_kkeg),
                 ("TOPLAM KKEG", kkeg),
                 ("DÖNEM KARI / ZARARI", donem_kari),
                 ("İştirak Kazancı İstisnası (-) (KVK 5/1-a)", istirak),
                 ("Mahsup Edilen Geçmiş Yıl Zararı (-)", mahsup),
                 ("Bağış ve Yardımlar (-) (%5 sınırlı)", bagis_ind),
                 ("Tamamı İndirilen Bağışlar (-)", tam_ind),
                 ("Ar-Ge İndirimi (-)", arge_ind),
                 ("Sonraki Yıla Devreden Ar-Ge İndirimi", arge_devreden),
                 ("MALİ KAR (MATRAH)", max(0.0, matrah)),
                 ("Sonraki Yıla Devreden Zarar", devreden),
                 (f"HESAPLANAN KURUMLAR VERGİSİ (%{vergi_orani * 100:g})", vergi),
                 ("ÖDENEN GEÇİCİ VERGİ (193)", pesin),
                 ("ÖDENECEK VERGİ / (İADE)", vergi - pesin),
                 ("VERGİ SONRASI DÖNEM NET KARI", donem_kari - vergi)]

    # --- RASYOLAR ---
    def bol(a, b):
        return a / b if b else None
    stoklar = sum(at_ for typ, g, _, at_ in aktif if typ == "grup" and g == "15")
    hazir = sum(at_ for typ, g, _, at_ in aktif if typ == "grup" and g == "10")
    rasyo = [("Cari Oran", bol(at["1"], pt["3"])),
             ("Asit-Test Oranı", bol(at["1"] - stoklar, pt["3"])),
             ("Nakit Oranı", bol(hazir, pt["3"])),
             ("Finansal Kaldıraç (Yabancı Kaynak / Pasif)", bol(yabanci, pasif_top)),
             ("Öz Kaynak / Pasif", bol(oz, pasif_top)),
             ("Yabancı Kaynak / Öz Kaynak", bol(yabanci, oz)),
             ("Aktif Devir Hızı", bol(net_satis, aktif_top)),
             ("Öz Kaynak Kârlılığı (ROE)", bol(donem_kari, oz)),
             ("Aktif Kârlılığı (ROA)", bol(donem_kari, aktif_top))]

    return {"envanter": envanter, "gelir_tablosu": gelir_tablosu, "net_satis": net_satis,
            "aktif": aktif, "pasif": pasif, "fark": fark, "fgk": fgk, "vergi": vergi_tab,
            "rasyo": rasyo, "uyarilar": uyarilar, "donem_kari": donem_kari, "smm": smm_ozet, "analiz": analiz}
