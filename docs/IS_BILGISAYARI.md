# İş bilgisayarı rehberi (doğrulama oturumları)

Bu dosya, iş bilgisayarında [VALIDATION.md](VALIDATION.md) yürütülürken bu kuruluma özgü
farkları ve sırayı tutar. Komutların ve beklenen sonuçların asıl kaynağı VALIDATION.md'dir;
burada yalnızca onunla çelişmeyen ekler var. Her oturumda önce `git pull`, sonra bu dosyanın
**Durum** bölümü.

Gizlilik: bu dosyaya ve VALIDATION.md'ye iş yeri makine adı, IP, kullanıcı adı, kampanya yolu
yazılmaz. Depo bir gün açık olacak; geçmişteki her satır da açılır.

## Durum

- Güncelleme: 2026-11-05
- Veri seti açık: `D:\altum-pt-blueberries-60m-sample-data\altum-pt-blueberries-60m-sample-data`
  (tek klasör; 3.361 dosya bekleniyor, 2.1'deki sayımlarla doğrulanacak).
- Uçuş düzeni (Pix4D harita görünümünden): hatlar kuzey-güney, gidiş-dönüş; başlangıç batı
  kenarının ortası (ilk hat yarım), her hattan sonra doğuya kayıyor, bitiş kuzeydoğu köşesi.
  Bu, V75'in beklenen cevabıdır.
- Veri setinde iki panel çekimi var (önceki varsayımın tersine): `IMG_0000` kalkış öncesi,
  `IMG_0479` iniş sonrası, yerde, elle tetiklenmiş. VALIDATION.md V14, V20, V42 buna göre
  düzeltildi.
- Pix4D (Pix4Dmapper 4.10.1; adımlar her zaman tek tek başlatılır): ilk iki proje
  (`altum-pt-blueberries` 3D Maps, `altum-pt-blueberries-ag` Ag Multispectral) silindi.
  Teşhis (iki `.p4d` ve iki logun karşılaştırması, 2026-11-03): 1. adım ayarları aynıydı
  (Standard, iç parametreler All, rig "optimize relative rotation using a subset of secondary
  cameras", ±5°). Rig dönüşleri kalibrasyonun başında, yalnız 9 yeşil çekim varken serbest
  kalıp kayıyordu (fabrika < 1°, sonuç 95°'ye kadar); bundle patladı, ilk projenin bitmesi
  şanstı. Ayrıca `IMG_0478_7` içe aktarılmamış (`IMG_0478` devre dışı kaldı) ve panel
  görüntüsü `IMG_0479_6` projede kalmıştı. Sonradan görüntü eklenemediği için yeni proje.
- `altum-pt-blueberries-v2` (2026-11-04/05) üç adımı da bitti:
  - 1. adım: rig modu **Rely on Relatives** (raporda "rely on relatives and match only reference
    camera"; yalnız referans kamera, yeşil, eşleşir ve iç parametreleri optimize edilir, diğer
    bantlar fabrika rig değerleriyle bağlı). 3.346/3.346 kalibre (14 panel görüntüsü devre
    dışı), rig dönüşleri başlangıç değerinde (en büyüğü LWIR 0,915°), yeşil R1 −0,135, yeniden
    izdüşüm 0,122 px, tek blok, GSD 2,72 cm, alan 9,55 ha, 9 dk 49 sn.
  - 2. adım: şablon değerleri (yarım ölçek, düşük yoğunluk), 2,61 milyon nokta, 1 dk 44 sn.
    GPU ayarı *Processing Options → Resources and Notifications* altında (A4000 seçili); raporun
    "unknown graphics card" satırı yalnız raporlama.
  - 3. adım: altı optik bant **Camera and Sun Irradiance** ve panel hedefiyle (Pix4D panel
    görüntüsünü, `IMG_0479`, ve poligonu kendisi buldu), LWIR **No Correction**; reflektans
    haritaları 1 × GSD, 52 dk.
  - **Açık 1:** raporda DSM ve ortomozaik süreleri 0 sn; ortomozaik ve Google Maps Tiles/KML
    büyük olasılıkla üretilmedi (şablonda kapalı). V20c'ye gelince bakılacak; 3. adım bunun için
    yeniden başlatılmaz (yeniden başlatma reflektans haritalarını siler).
  - **Açık 2:** panel albedo değerleri (CSV'deki bant merkezleriyle) doğrulanmadı; raporda
    yazmıyor. `.p4d` dosyası Mac'teki oturuma gönderilince kontrol edilecek.
- Faz 1: sürüyor. Takılma kaydının ilk dört satırı VALIDATION.md'ye yazıldı ve README düzeltildi
  (winget/git kontrolü, Git kurulumu, yeni pencere). **Sıradaki:** Faz 1 klasöründe `git pull`,
  `uv sync`, P5-P7 (yalnız README'ye bakarak). Faz 2-5: başlamadı.

## 1. Pix4D: yeni proje `altum-pt-blueberries-v2`

Hedef: bantları birbirine hizalı, panelle kalibre edilmiş reflektans haritaları. Doğrulama
bunlardan V20c'nin KML'ini ve ekran görüntülerini kullanır; README'nin "Pix4Dmapper ile
denendi" cümlesi de bu projeye dayanır.

**A. Proje ve görüntüler**

1. *Yeni Proje* → ad `altum-pt-blueberries-v2`, konum `D:\altum-pt-blueberries-60m-sample-data\`
   (veri klasörünün yanı, içi değil).
2. *Add Images*: veri klasöründeki 3.360 TIFF'in **hepsi** (panel çekimleri dahil; panel
   kalibrasyonu için projede olmaları gerekir).
3. Görüntü özellikleri ekranında:
   - kamera Altum-PT (rig «Altum-PT»), 7 kamera modeli;
   - görüntü sayısı **3.360**; `IMG_0478_1` … `IMG_0478_7` yedisi de var;
   - koordinat sistemi: görüntüler WGS 84 (EGM 96 Geoid), çıktı WGS 84 / UTM zone 10N. Dikey
     referansı projeler arasında karıştırma (eski iki proje farklıydı).
4. Şablon **Ag Multispectral**, *İşlemeye Başla* **işaretsiz** → *Finish*.
5. *Image Properties Editor*: panel çekimleri `IMG_0000_1-7` ve `IMG_0479_1-7` (14 görüntü)
   **devre dışı** (Enabled işaretsiz). Geri kalan 3.346 görüntü etkin, `IMG_0478` dahil.

**B. 1. adım ayarları** (*İşleme Seçenekleri → 1. Initial Processing*)

6. Şablonun değerlerini koru (Keypoints Full, Aerial Grid or Corridor, Calibration Method
   Standard, Internal Parameters Optimization All) ve **tek bir şeyi** değiştir: rig göreli
   dönüşlerini optimize ettirmeyen seçenek. Şu anki değer "optimize relative rotation using a
   subset of secondary cameras". Yer: *Calibration* sekmesi; orada yoksa *Image Properties
   Editor → Camera Model / Rig → Edit*. Tam adı doğrulanmadı: bulamazsan ekran görüntüsünü
   Mac'teki oturuma gönder, tahminle seçme.
7. *OK*, projeyi kaydet, yalnız **1. adımı** başlat. Log penceresinin başındaki `Active GPU`
   satırını not et ("Microsoft Remote Display Adapter" ise Pix4D A4000'i kullanmıyor; Yardım →
   Ayarlar'da A4000'i seç).

**C. 1. adımın kabulü** (kalite raporu, Mac'teki oturuma gönderilir)

- kalibre görüntü 3.346'ya yakın (devre dışı 14 panel görüntüsü hariç);
- rig göreli dönüşleri bütün bantlarda < 1° (başlangıç değerleri gibi);
- *2D Keypoints Table*: her kamera modelinde eşleşen nokta medyanı > 0;
- *Camera Optimization* göreli farkı birkaç yüzdenin altında; iç parametrelerde anlamsız değer
  yok (R1 yaklaşık −0,14 civarında);
- tek blok.

Geçmezse: iç parametreler kaydıysa ikinci deneme rig sabit + *Internal Parameters
Optimization* **All Prior**. Başka bir sorun varsa raporla birlikte dur.

**D. 2. ve 3. adım** (1. adım kabul edildikten sonra)

8. 2. adım şablonla.
9. 3. adımdan önce:
   - ortomozaik açık, **Google Maps Tiles and KML** işaretli (V20c'deki "Pix4D alan KML'i").
     KML **klonun dışında** (`$Res`) tutulur, commit edilmez;
   - Index Calculator → radyometrik düzeltme: blue, green, red, red edge, NIR, panchro
     **Camera and Sun Irradiance** + *Kalibre Et*: her bant için kendi panel görüntüsü
     (`IMG_0000_<bant no>`, panel gölgesiz ve tamamen görünür değilse `IMG_0479_<bant no>`),
     panel üzerine poligon, albedo değeri veri setindeki panel CSV'sinden o bandın merkez dalga
     boyunda. LWIR **No Correction** (Camera Only termali sabit kazançla ölçekliyor).
10. 3. adımı başlat.

Bant numaraları ve merkez dalga boyları (Altum-PT): 1 blue 475 nm, 2 green 560 nm, 3 red
668 nm, 4 NIR 842 nm, 5 red edge 717 nm, 6 panchro (geniş bant; CSV'nin o aralıktaki
ortalaması), 7 LWIR. Bant numarası sırasını Pix4D'deki kamera modeli adlarıyla doğrula.

## 2. Klasörler (VALIDATION.md 2.1'in yerine)

Veri D: sürücüsünde kalıyor; Pix4D projesi görüntü yollarını tuttuğu için klasör taşınmaz.
Sabit bağlantı (hardlink) kontrolleri aynı sürücü istediği için çalışma klasörü de D:'de.
Her PowerShell oturumunun başında VALIDATION.md 2.1'deki bloğu **bu değerlerle** çalıştır:

```powershell
$Demo = "D:\uav-demo"
$Repo = "$Demo\uav-aoi-subset"
$Data = "D:\altum-pt-blueberries-60m-sample-data\altum-pt-blueberries-60m-sample-data"
$Lay  = "$Demo\data\blueberry_layered"
$Aoi  = "$Demo\aoi"
$Res  = "$Demo\results"
New-Item -ItemType Directory -Force $Demo, "$Demo\data", $Aoi, $Res | Out-Null
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$env:PYTHONUTF8 = "1"
function aoi { uv run --project $Repo uav-aoi-subset @args }
```

VALIDATION.md'de `C:\uav-demo` geçen her yer bu kurulumda `D:\uav-demo` olarak okunur. Faz 1
README'nin önerdiği klasörle (`C:\uav-demo\phase1`) yapılır, ona dokunulmaz.

Disk: başlamadan `Get-PSDrive C, D` ile boş alana bak. D:'de en az **90 GB** gerekir: V12
veri setinin tamamını (25,4 GB) kopyalar, V34 tam kopya yapar (25,4 GB), V39 onun bir kopyasını
daha alır (25,4 GB). Her birini kendi kontrolü bittikten hemen sonra sil
(`Saha Fotoğrafları – deneme`, `move_src`, `move_dst`); `full_copy`'yi V39 bitene kadar tut.

## 3. Sıra ve bu kuruluma özgü notlar

Faz 1 yalnız README ile yapılır: o bitene kadar bu bölümü ve VALIDATION.md'nin Faz 1 sonrasını
okuma.

| Kontrol | Bu kurulumda |
|---|---|
| 2.1 sayımlar | `$Data` yukarıdaki yol; `Move-Item` adımı atlanır, sayım komutları aynen çalıştırılır |
| V12 | kopya D:'ye gider (25,4 GB); kontrolden sonra sil |
| V20c | Pix4D KML'i 1. bölümdeki `-v2` projesinin 3. adımından |
| V37, V40 | `$Data` ile aynı sürücü (D:) olmalı; yukarıdaki değerlerle öyle |
| V43, V44 | "diğer sürücü" bu kurulumda **C:** (`--dest C:\uav-demo-other\...`); sonra sil |
| V50-V52 | tüm veriyle açılan proje değil, V31'in alt küme klasörüyle **ayrı yeni** proje (şablon Ag Multispectral) |
| V60 | beklenen yol `C:\uav-demo\data\blueberry` değil, `$Data` yolu |
| V75 | beklenen: kuzey-güney hatlar, gidiş-dönüş, doğuya kayarak (Durum bölümü) |
| V76a | dört şerit batıdan doğuya `0000SET` → `0003SET`; her biri yaklaşık dört hat; ilk hat yarım olduğu için şerit sınırları hat ortasına düşebilir, bu hata değil |
| 2.7, V79, V84 | MATLAB bu bilgisayarda yoksa n.a. yazılır ve nedeni not edilir |
| Faz 4-5 | kampanya verisi; çıktılar `C:\uav-demo\private` yerine `D:\uav-demo\private`; yalnız anonim sayılar |

Ek, isteğe bağlı (VALIDATION.md'de yok, V92'nin yerini tutmaz): `D:\altum-pt-blueberries-60m-sample-data`
klasörü hem veriyi hem Pix4D projelerini içeriyor. `aoi index` bu üst klasörde çalıştırılırsa
Pix4D'nin yazdığı dosyaların nasıl sayıldığı açık veriyle görülür; sonuç "Findings" altına not
olarak yazılabilir.

## 4. Sonuçlar ve gönderim

- Sonuçlar VALIDATION.md'nin *Results* tablolarına, yalnız sayılarla. Her bulgu GitHub'da
  *Bug report* formuyla issue.
- Her oturum sonunda: `git status` (yalnız `docs/` değişmeli), commit, `git push`,
  `git log origin/main -1` ile gönderimi doğrula. Clone geçici, gönderilmeyen sonuç kaybolur.
- Bu dosyanın **Durum** bölümünü de güncelle (hangi faz, hangi kontrol, açık sorular).
- Takılınca: Mac'teki Claude oturumuna "IS_BILGISAYARI.md durumuna bak" demek yeter; ekran
  görüntüsü ya da çıktı da eklenebilir.
