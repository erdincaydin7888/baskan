"""Kendi kendini sınar: python test_baskan.py  (uydurma örnek mizanla, gerçek veri kullanmaz)"""
import sys, tempfile, os
import pandas as pd
import mizan, motor

STOK_153 = 90_000_000.0  # dönem başı + alışlar (aralıklı envanter)
DS = 25_000_000.0        # dönem sonu sayım stoku
KAR = 20_800_000.0       # 99M net satış − 65M SMM − 11M faaliyet + 0,3M faiz geliri − 2,5M finansman


def ornek_mizan():
    """Uydurma kebir mizanı: aralıklı envanterli ticari işletme. 950/951 'Bakiye' sütunu bilerek yanlış."""
    hesap = [("100", "KASA", 5e6, 3e6), ("102", "BANKALAR", 70e6, 60e6), ("120", "ALICILAR", 60e6, 45e6),
             ("153", "TİCARİ MALLAR", STOK_153, 0), ("193", "PEŞİN ÖDENEN VERGİLER", 2e5, 0),
             ("255", "DEMİRBAŞLAR", 10e6, 0), ("257", "BİRİKMİŞ AMORTİSMANLAR", 0, 2e6),
             ("300", "BANKA KREDİLERİ", 10e6, 50e6), ("320", "SATICILAR", 30e6, 75e6),
             ("500", "SERMAYE", 0, 10e6), ("600", "YURTİÇİ SATIŞLAR", 0, 100e6), ("610", "SATIŞTAN İADELER", 1e6, 0),
             ("642", "FAİZ GELİRLERİ", 0, 3e5), ("760", "PAZARLAMA SATIŞ DAĞITIM GİDERLERİ", 8e6, 0),
             ("770", "GENEL YÖNETİM GİDERLERİ", 3e6, 0), ("780", "FİNANSMAN GİDERLERİ", 2.5e6, 0),
             ("950", "KANUNEN KABUL EDİLMEYEN GİDERLER", 4e5, 0), ("951", "KKEG YANSITMA", 0, 4e5)]
    fark = sum(b - a for _, _, b, a in hesap)  # borç = alacak olsun diye fark bankaya kapatılır
    hesap = [(k, ad, b - fark if k == "102" else b, a) for k, ad, b, a in hesap]
    yanlis = {"950": 5e5, "951": -5e5}
    rows = [[k, ad, b, a, yanlis.get(k, b - a)] for k, ad, b, a in hesap]
    p = os.path.join(tempfile.mkdtemp(), "ornek_mizan.xlsx")
    pd.DataFrame(rows, columns=["Hesap Kodu", "Hesap Adı", "Borç", "Alacak", "Bakiye"]).to_excel(p, index=False)
    return p


def sina(yol):
    h, uy, (_, satir, es) = mizan.oku(yol)
    print("eşleşme:", {mizan.ROL_AD[k]: v for k, v in es.items()}, "başlık satırı:", satir)
    assert any(u.startswith("950") for u in uy), "950 bakiye uyumsuzluğu yakalanmalı"
    r = motor.hesapla(h, stok=DS)
    assert r["fark"] == 0, r["fark"]
    assert abs(r["donem_kari"] - KAR) < 0.01, r["donem_kari"]
    assert abs(r["net_satis"] - 99e6) < 0.01
    smm = r["smm"]["smm"]
    assert abs(smm - (STOK_153 - DS)) < 0.01
    ns = r["net_satis"]
    # FGK: yabancı kaynak 85M, öz kaynak 10M + kâr; aşan oran × finansman gideri × %10
    oz = 10e6 + KAR
    fgk = 2.5e6 * (85e6 - oz) / 85e6 * 0.10
    assert abs(r["fgk"][-1][2] - fgk) < 0.01, r["fgk"][-1]
    M = KAR + 4e5 + fgk  # mali kâr
    # Brüt kâr oranı: SMM = net satış × (1 − oran), dönem sonu stok = satılabilir − SMM, bilanço dengede
    rm = motor.hesapla(h, yontem="marj", kar_marji=0.20)
    assert rm["fark"] == 0, rm["fark"]
    assert abs(rm["smm"]["smm"] - ns * 0.80) < 0.01
    assert abs(rm["smm"]["donem_sonu_stok"]["153"] - (STOK_153 - ns * 0.80)) < 0.01
    assert abs(rm["smm"]["brut_oran"] - 0.20) < 1e-9
    # Elle stok: mizandaki tutar girilirse marj yöntemiyle aynı, miktar ortalama maliyetle
    rl = motor.hesapla(h, yontem="elle", kar_marji=0.20, elle_tutar=STOK_153, elle_miktar=1000)
    assert rl["fark"] == 0 and abs(rl["donem_kari"] - rm["donem_kari"]) < 0.01
    assert abs(rl["smm"]["ds_miktar"] - 1000 * (1 - ns * 0.80 / STOK_153)) < 1e-6
    # Üretim: 150/151/152 stok farkı + 71x/72x/73x → 620, 74x → 622; bilanço dengede
    u = {k: dict(v) for k, v in h.items()}
    ek = {"150": 500.0, "151": 300.0, "152": 200.0, "710": 1000.0, "720": 400.0, "730": 250.0, "740": 50.0}
    for kod, t in ek.items():
        u[kod] = {"ad": kod, "bakiye": t}
    u.setdefault("320", {"ad": "SATICILAR", "bakiye": 0.0})["bakiye"] -= sum(ek.values())
    ru = motor.hesapla(u, ds_stok={"150": 100, "151": 50, "152": 80, "153": DS})
    assert ru["fark"] == 0, ru["fark"]
    s620 = next(t for tur, kod, _, t in ru["envanter"] if tur == "ara" and kod == "620")
    assert abs(s620 - ((500 - 100 + 1000) + 400 + 250 + (300 - 50) + (200 - 80))) < 0.01, s620
    assert abs(ru["smm"]["smm"] - (smm + s620 + 50)) < 0.01
    rum = motor.hesapla(u, yontem="marj", kar_marji=0.20)
    assert rum["fark"] == 0 and abs(rum["smm"]["smm"] - ns * 0.80) < 0.01
    # Mizanda 691 / 370 vergi karşılığı kayıtlıysa bilanço net kârla dengede kalmalı
    v = {k: dict(x) for k, x in h.items()}
    v["691"] = {"ad": "VERGİ KARŞILIĞI", "bakiye": 400000.0}
    v["370"] = {"ad": "VERGİ KARŞILIĞI", "bakiye": -400000.0}
    rv = motor.hesapla(v, stok=DS)
    assert rv["fark"] == 0, rv["fark"]
    assert any("691" in x for x in rv["uyarilar"])
    v = dict(r["vergi"])
    print("dönem kârı", r["donem_kari"], "FGK KKEG", r["fgk"][-1][2], "matrah", v["MALİ KAR (MATRAH)"])
    assert abs(v["MALİ KAR (MATRAH)"] - M) < 0.01
    # İştirak istisnası zararda da düşer, geçmiş yıl zararı yalnız kalan kârdan ve en çok onun kadar
    v = dict(motor.hesapla(h, stok=DS, istirak=1e6, gecmis_zarar=5e5)["vergi"])
    assert abs(v["MALİ KAR (MATRAH)"] - (M - 1e6 - 5e5)) < 0.01
    assert v["Sonraki Yıla Devreden Zarar"] == 0
    v = dict(motor.hesapla(h, stok=DS, istirak=1e6, gecmis_zarar=M)["vergi"])
    assert v["MALİ KAR (MATRAH)"] == 0 and abs(v["Mahsup Edilen Geçmiş Yıl Zararı (-)"] - (M - 1e6)) < 0.01
    assert abs(v["Sonraki Yıla Devreden Zarar"] - 1e6) < 0.01
    v = dict(motor.hesapla(h, stok=DS, istirak=M + 5e6, gecmis_zarar=100)["vergi"])
    assert v["MALİ KAR (MATRAH)"] == 0 and v["Mahsup Edilen Geçmiş Yıl Zararı (-)"] == 0
    assert abs(v["Sonraki Yıla Devreden Zarar"] - (100 + 5e6)) < 0.01
    # Ar-Ge + bağış: zarar mahsubundan sonra, bağış %5 sınırlı, kalan kazançla sınırlı
    v = dict(motor.hesapla(h, stok=DS, arge=1e6, bagis=5e6, bagis_tam=1e5)["vergi"])
    assert abs(v["Bağış ve Yardımlar (-) (%5 sınırlı)"] - M * 0.05) < 0.01
    assert abs(v["MALİ KAR (MATRAH)"] - (M - 1e6 - M * 0.05 - 1e5)) < 0.01
    v = dict(motor.hesapla(h, stok=DS, arge=M + 5e6, bagis=1000)["vergi"])
    assert v["MALİ KAR (MATRAH)"] == 0 and v["Bağış ve Yardımlar (-) (%5 sınırlı)"] == 0
    assert abs(v["Sonraki Yıla Devreden Ar-Ge İndirimi"] - 5e6) < 0.01
    # Stok girilmeden de bilanço dengede olmalı
    assert motor.hesapla(h)["fark"] == 0
    # Aynı mizan: alt hesaplı + farklı başlıklı + TR sayı biçimli + üst satırda firma başlığı
    df = pd.read_excel(yol, dtype=object)
    satirlar = [["ÖRNEK A.Ş. 01.01-31.12 MİZANI", None, None, None], [None] * 4,
                ["Hesap No", "Açıklama", "Toplam Borç", "Toplam Alacak"]]
    for _, x in df.iterrows():
        k = str(x["Hesap Kodu"])
        satirlar.append([k, x["Hesap Adı"], mizan.tl(x["Borç"]), mizan.tl(x["Alacak"])])  # kebir satırı
        b1, a1 = round(x["Borç"] / 2, 2), round(x["Alacak"] / 2, 2)
        satirlar.append([k + ".01", "alt1", mizan.tl(b1), mizan.tl(a1)])
        satirlar.append([k + ".01.001", "alt-alt", mizan.tl(b1), mizan.tl(a1)])
        satirlar.append([k + ".02", "alt2", mizan.tl(x["Borç"] - b1), mizan.tl(x["Alacak"] - a1)])
    satirlar.append(["GENEL TOPLAM", None, "1", "1"])
    d = tempfile.mkdtemp()
    for adi, sil_kebir in (("kebirli.xlsx", False), ("yalniz_alt.xlsx", True)):
        rows = [s for s in satirlar if not (sil_kebir and s[0] and s[0][:3].isdigit() and len(s[0]) == 3)]
        p = os.path.join(d, adi)
        pd.DataFrame(rows).to_excel(p, header=False, index=False)
        h2, *_ = mizan.oku(p)
        r2 = motor.hesapla(h2, stok=DS)
        assert r2["fark"] == 0 and abs(r2["donem_kari"] - KAR) < 0.01, (adi, r2["donem_kari"])
    # CSV ; ayraçlı, tek bakiye sütunu + B/A işareti
    p = os.path.join(d, "m.csv")
    with open(p, "w", encoding="cp1254") as f:
        f.write("Kod;Hesap Adı;Bakiye;B/A\n")
        for _, x in df.iterrows():
            b = x["Borç"] - x["Alacak"]
            f.write(f"{x['Hesap Kodu']};{x['Hesap Adı']};{mizan.tl(abs(b))};{'B' if b >= 0 else 'A'}\n")
    h3, *_ = mizan.oku(p)
    r3 = motor.hesapla(h3, stok=DS)
    assert r3["fark"] == 0 and abs(r3["donem_kari"] - KAR) < 0.01, r3["donem_kari"]
    assert mizan.sayi("(1.250,50)") == -1250.5 and mizan.sayi("1,234,567.89") == 1234567.89
    assert mizan.sayi("500.000") == 500000 and mizan.sayi("1.500") == 1500 and mizan.sayi("12.5") == 12.5
    assert mizan.sayi("1234.56") == 1234.56 and mizan.sayi("25") == 25
    print("TÜM TESTLER GEÇTİ")


def erp_mizani(d, ad, satirlar, devirli=False):
    """(kod, borç, alacak) listesinden kebir mizanı yaz; fark 500 sermayeye kapatılır (borç = alacak)."""
    fark = sum(b - a for _, b, a in satirlar)
    satirlar = satirlar + [("500", 0.0, fark) if fark > 0 else ("500", -fark, 0.0)]
    if devirli:  # Netsis/Logo tarzı: toplam sütunu yok, devir + dönem ayrı (devir = yarısı)
        rows = [["Hesap Kodu", "Hesap Adı", "Devir Borç", "Devir Alacak", "Borç", "Alacak", "Bakiye"]]
        rows += [[k, k, b / 2, a / 2, b / 2, a / 2, b - a] for k, b, a in satirlar]
    else:
        rows = [["Hesap Kodu", "Hesap Adı", "Borç", "Alacak"]] + [[k, k, b, a] for k, b, a in satirlar]
    p = os.path.join(d, ad)
    pd.DataFrame(rows).to_excel(p, header=False, index=False)
    return mizan.oku(p)[0]


def erp_sina():
    d = tempfile.mkdtemp()
    # 1) Sürekli envanter ticari mal: 621 kayıtlı -> giriş gerekmez, SMM = 621
    h = erp_mizani(d, "surekli.xlsx", [("600", 0, 1000), ("153", 1000, 700), ("621", 700, 0), ("102", 1000, 1000)])
    r = motor.hesapla(h, yontem="oto")
    assert r["analiz"]["gerekli"] == [] and r["analiz"]["hesap"]["153"][0] == "sürekli", r["analiz"]
    assert abs(r["smm"]["smm"] - 700) < 0.01 and r["fark"] == 0
    # 2) Aralıklı ticari mal: 621 yok, 153 alacağı yok -> 153 sayımı istenir; sayım ya da oranla hesaplanır
    h = erp_mizani(d, "aralikli.xlsx", [("600", 0, 1000), ("153", 900, 0), ("102", 1000, 900)])
    r = motor.hesapla(h, yontem="oto")
    assert r["analiz"]["gerekli"] == ["153"] and any(u.startswith("SMM EKSİK") for u in r["uyarilar"])
    r = motor.hesapla(h, yontem="oto", ds_stok={"153": 200})
    assert abs(r["smm"]["smm"] - 700) < 0.01 and r["fark"] == 0 and r["analiz"]["secilen"] == "envanter"
    r = motor.hesapla(h, yontem="oto", kar_marji=0.30)
    assert abs(r["smm"]["smm"] - 700) < 0.01 and r["fark"] == 0 and r["analiz"]["secilen"] == "marj"
    # 3) Sürekli üretim, 7/A yansıtmalı: 150->710, 711/721/731->151, 151->152, 152->620
    h = erp_mizani(d, "uretim_surekli.xlsx", [
        ("600", 0, 1000), ("150", 500, 400), ("710", 400, 0), ("711", 0, 400), ("720", 200, 0), ("721", 0, 200),
        ("730", 100, 0), ("731", 0, 100), ("151", 700, 700), ("152", 700, 600), ("620", 600, 0),
        ("102", 1000, 800)])
    r = motor.hesapla(h, yontem="oto")
    assert r["analiz"]["gerekli"] == [], r["analiz"]
    assert abs(r["smm"]["smm"] - 600) < 0.01 and r["fark"] == 0
    # 4) Aralıklı üretim: malzeme tüketimi kaydedilmemiş -> 150 sayımı istenir
    h = erp_mizani(d, "uretim_aralikli.xlsx", [("600", 0, 1000), ("150", 500, 0), ("720", 200, 0),
                                                 ("730", 100, 0), ("102", 1000, 800)])
    r = motor.hesapla(h, yontem="oto")
    assert r["analiz"]["gerekli"] == ["150"], r["analiz"]
    r = motor.hesapla(h, yontem="oto", ds_stok={"150": 100})
    assert abs(r["smm"]["smm"] - 700) < 0.01 and r["fark"] == 0
    # 5) Devir + dönem sütunlu mizan (toplam sütunu yok): ikisi toplanmalı
    h = erp_mizani(d, "devirli.xlsx", [("600", 0, 1000), ("153", 1000, 700), ("621", 700, 0),
                                         ("102", 1000, 1000)], devirli=True)
    assert abs(h["153"]["bakiye"] - 300) < 0.01 and abs(h["153"]["alacak"] - 700) < 0.01, h["153"]
    r = motor.hesapla(h, yontem="oto")
    assert abs(r["smm"]["smm"] - 700) < 0.01 and r["fark"] == 0
    print("ERP TESTLERİ GEÇTİ")

erp_sina()
sina(ornek_mizan())
