# İş bilgisayarı rehberi (doğrulama oturumları)

Bu dosya, iş bilgisayarında [VALIDATION.md](VALIDATION.md) yürütülürken bu kuruluma özgü
farkları ve sırayı tutar. Komutların ve beklenen sonuçların asıl kaynağı VALIDATION.md'dir;
burada yalnızca onunla çelişmeyen ekler var. Her oturumda önce `git pull`, sonra bu dosyanın
**Durum** bölümü.

Gizlilik: bu dosyaya ve VALIDATION.md'ye iş yeri makine adı, IP, kullanıcı adı, kampanya yolu
yazılmaz. Depo bir gün açık olacak; geçmişteki her satır da açılır.

## Durum

- Güncelleme: 2026-11-03
- Veri seti açık: `D:\altum-pt-blueberries-60m-sample-data\altum-pt-blueberries-60m-sample-data`
  (tek klasör; 3.361 dosya bekleniyor, 2.1'deki sayımlarla doğrulanacak).
- Uçuş düzeni (Pix4D harita görünümünden): hatlar kuzey-güney, gidiş-dönüş; başlangıç batı
  kenarının ortası (ilk hat yarım), her hattan sonra doğuya kayıyor, bitiş kuzeydoğu köşesi.
  Bu, V75'in beklenen cevabıdır.
- Veri setinde iki panel çekimi var (önceki varsayımın tersine): `IMG_0000` kalkış öncesi,
  `IMG_0479` iniş sonrası, yerde, elle tetiklenmiş. VALIDATION.md V14, V20, V42 buna göre
  düzeltildi.
- Pix4D, iki proje (Pix4Dmapper 4.10.1; adımlar her zaman tek tek başlatılır):
  - `altum-pt-blueberries` (3D Maps): 1. adım "bitti" ama kullanılamaz. Kalite raporunda
    yalnız yeşil bantta 3D iz var; rig göreli dönüşleri fabrika değerlerinden (< 1°) 95°'ye
    kadar kaymış, NIR ve mavide iç parametreler anlamsız. Dokunma, karşılaştırma için kalsın.
  - `altum-pt-blueberries-ag` (Ag Multispectral): 1. adım `e0046 No calibrated cameras`.
  - Teşhis (iki `.p4d` ve iki logun karşılaştırması, 2026-11-03): iki projenin 1. adım ayarları
    aynı (Standard, iç parametreler All, rig modu "optimize relative rotation using a subset of
    secondary cameras", ±5°). Rig dönüşleri kalibrasyonun başında, yalnız 9 yeşil çekim varken
    serbest kalıyor ve bundle patlıyor; birinci projenin bitmesi şans. Ham eşleşmeler bütün
    bantlarda var.
  - Projeye 3.346 görüntü girmiş: `IMG_0000_1-7` ve `IMG_0479_1-5,7` (panel) alınmamış,
    `IMG_0479_6` radyometri görüntüsü olarak tutulmuş; `IMG_0478_7` nedeni bilinmeden eksik, bu
    yüzden `IMG_0478` tutarsız çekim sayılıp devre dışı. Doğrulamayı etkilemez.
  - **Sıradaki:** 1. bölüm: rig dönüşlerini sabitleyip `-ag` projesinde 1. adımı yeniden çalıştır.
- Faz 1: sürüyor. Takılma kaydının ilk dört satırı VALIDATION.md'ye yazıldı ve README düzeltildi
  (winget/git kontrolü, Git kurulumu, yeni pencere). Sıradaki: README'yi `git pull` ile tazele,
  `uv sync`, P5-P7. Faz 2-5: başlamadı.

## 1. Pix4D: rig dönüşleri sabit, `-ag` projesinde 1. adım

Doğrulama için Pix4D'den gerekenler: bantların aynı çekime gruplanması (V50, V77e; içe
aktarmada olur), görüntülenen alanın KML'i (V20c) ve ekran görüntüleri. Bantları hizalı doğru
bir sonuç, README'nin "Pix4Dmapper ile denendi" cümlesinin dürüst olması için gerekli.

1. `altum-pt-blueberries` projesine dokunma. Deneme `altum-pt-blueberries-ag` projesinde
   (zaten başarısız, kaybedilecek bir şey yok).
2. Rig göreli dönüşlerini **optimize ettirmeyen** seçeneği bul ve seç. Bakılacak yerler:
   *İşleme Seçenekleri → 1. Initial Processing → Calibration* (rig işleme seçeneği,
   şu anki değer "optimize relative rotation using a subset of secondary cameras"); orada
   yoksa *Image Properties Editor → Camera Model / Rig → Edit*. Tam adı doğrulanmadı;
   bulamazsan iki pencerenin ekran görüntüsünü Mac'teki oturuma gönder.
3. 1. adımın diğer ayarlarına dokunma (Standard, iç parametreler All). Tek değişken rig.
4. Yalnız 1. adımı çalıştır.
5. Başarı ölçütleri (kalite raporu): bütün bantlarda rig dönüşleri < 1°; *2D Keypoints
   Table* içinde her bandın eşleşen nokta medyanı > 0; *Camera Optimization* göreli farkı
   birkaç yüzdenin altında (şu an %61); tek blok. Raporu Mac'teki oturuma gönder.
6. İç parametreler yine kayarsa, ikinci deneme: rig sabit + *Internal Parameters
   Optimization* **All Prior**.
7. 1. adım temizse 2. adım. 3. adımdan önce: ortomozaik açık ve **Google Maps Tiles and KML**
   işaretli (bu projede şablon kapattı; V20c'deki "Pix4D alan KML'i" bu olacak); Index
   Calculator beş reflektans bandı **Camera and Sun Irradiance**, LWIR **No Correction**
   (Camera Only termali sabit kazançla ölçekliyor). Panel kalibrasyonu doğrulama için gerekmez.
   KML yoksa QGIS'te bir reflektans haritasının geçerli piksellerinden poligon çıkar
   (Raster → Dönüştürme → Poligonlaştır). KML her durumda **klonun dışında** (`$Res`) kalır.
8. Log penceresinin başındaki `Active GPU` satırı "Microsoft Remote Display Adapter" diyorsa
   Pix4D A4000'i kullanmıyor: Pix4D ayarlarında (Yardım → Ayarlar) A4000'i seç, olmuyorsa not
   et. Doğrulamayı etkilemez, yalnız süreyi.

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
| V20c | Pix4D KML'i 1. bölümdeki `-ag` projesinin 3. adımından |
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
