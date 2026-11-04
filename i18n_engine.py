"""Turkish texts for the engine's messages (engine.py, translation.py, cuda_setup.py).

The engine writes its log lines and error messages in English (the command line stays
English). The window shows them through i18n.engine_message(), which matches every line
of a message against PATTERNS below: (regex, {"tr": template}). The regex must match the
whole stripped line; the template uses the regex's named groups. Lines that no pattern
matches are shown unchanged (in English).

Keep the patterns anchored to fixed English words, most specific first. When an engine
message changes, change its pattern here too (tests/test_i18n_engine.py has a sample line
for every pattern).

Technical details inside a message (file names, sizes, times, language codes, error
text from Windows/ffmpeg) are copied into the Turkish text unchanged.
"""

from __future__ import annotations

STRINGS: dict[str, dict[str, str]] = {}

# Building blocks.
_TIME = r"(?P<time>\d+(?::\d{2}){1,2})"           # engine._clock(): 0:05, 12:34, 1:02:03
_LANG = r"[A-Za-z]{2,3}(?:-[A-Za-z]{2,4})?"       # language codes: tr, en, zh-CN, yue
_SIZE = r"[^()]*"                                  # "75 MB", "1.6 GB" (may be empty)

# Fixed reasons of a failed online request (translation._short_reason) and MyMemory's limit.
_TOO_MANY = "too many requests; the service limits how much one computer can translate"
_TOO_MANY_TR = "çok fazla istek; hizmet tek bir bilgisayarın yapabileceği çeviriyi sınırlıyor"
_NO_CONNECTION = r"no connection to the service; is the internet on\?"
_NO_CONNECTION_TR = "hizmete bağlanılamadı; internet açık mı?"
_DAILY_LIMIT = "MyMemory daily limit reached"
_DAILY_LIMIT_TR = "MyMemory'nin günlük sınırı doldu"

PATTERNS: list[tuple[str, dict[str, str]]] = [
    # ---------------------------------------------------------------- general
    (r"Cancelled by user\.",
     {"tr": "Kullanıcı tarafından iptal edildi."}),
    (r"Done\.",
     {"tr": "Tamamlandı."}),

    # ---------------------------------------------------------------- input video, ffmpeg
    (r"Video not found: (?P<name>.+) \(was it moved or renamed\?\)",
     {"tr": "Video bulunamadı: {name} (taşınmış ya da adı değiştirilmiş olabilir)."}),
    (r"Choose at least one target language\.",
     {"tr": "En az bir çeviri dili seçin."}),
    (r"Could not create the output folder (?P<folder>.+) \((?P<reason>.+?)\)\.",
     {"tr": "Çıktı klasörü oluşturulamadı: {folder} ({reason})."}),
    (r"FFmpeg is missing \((?P<tool>.+?) not found\)\. Run setup\.bat again\.",
     {"tr": "FFmpeg bulunamadı ({tool} yok). setup.bat dosyasını yeniden çalıştırın."}),
    (r"If it still fails, restart Windows and try once more\.",
     {"tr": "Sorun sürerse Windows'u yeniden başlatıp bir kez daha deneyin."}),
    (r"Cannot open this file as a video \(damaged, incomplete or not a video\)\.",
     {"tr": "Bu dosya video olarak açılamadı (bozuk, eksik ya da video dosyası değil)."}),
    (r"This video has no sound track, so there is no speech to subtitle\.",
     {"tr": "Bu videoda ses yok; altyazıya dökülecek bir konuşma bulunmuyor."}),
    (r"Extracting audio with ffmpeg\.\.\.",
     {"tr": "Videonun sesi alınıyor (ffmpeg)..."}),
    (r"Could not read the sound of this video \(ffmpeg failed\)\.",
     {"tr": "Bu videonun sesi okunamadı (ffmpeg hata verdi)."}),

    # ---------------------------------------------------------------- model downloads
    (r"Downloading the speech recognition model '(?P<model>[^']+)' \((?P<size>" + _SIZE + r"), "
     r"only once\)\. This can take several minutes\.\.\.",
     {"tr": "Konuşma tanıma modeli '{model}' indiriliyor ({size}, yalnızca ilk seferde). "
            "Bu birkaç dakika sürebilir..."}),
    (r"Downloading the offline translation model \(about (?P<size>" + _SIZE + r"), only once\)\. "
     r"This can take several minutes\.\.\.",
     {"tr": "Çevrimdışı çeviri modeli indiriliyor (yaklaşık {size}, yalnızca ilk seferde). "
            "Bu birkaç dakika sürebilir..."}),
    (r"still downloading the speech recognition model \((?P<size>" + _SIZE + r")\), "
     r"(?P<n>\d+) min so far\. Please wait\.\.\.",
     {"tr": "Konuşma tanıma modeli hâlâ indiriliyor ({size}), {n} dakikadır sürüyor. Lütfen bekleyin..."}),
    (r"still downloading the speech recognition model \((?P<size>" + _SIZE + r")\), "
     r"(?P<n>\d+) s so far\. Please wait\.\.\.",
     {"tr": "Konuşma tanıma modeli hâlâ indiriliyor ({size}), {n} saniyedir sürüyor. Lütfen bekleyin..."}),
    (r"still downloading the translation model \(about (?P<size>" + _SIZE + r")\), "
     r"(?P<n>\d+) min so far\. Please wait\.\.\.",
     {"tr": "Çevrimdışı çeviri modeli hâlâ indiriliyor (yaklaşık {size}), {n} dakikadır sürüyor. "
            "Lütfen bekleyin..."}),
    (r"still downloading the translation model \(about (?P<size>" + _SIZE + r")\), "
     r"(?P<n>\d+) s so far\. Please wait\.\.\.",
     {"tr": "Çevrimdışı çeviri modeli hâlâ indiriliyor (yaklaşık {size}), {n} saniyedir sürüyor. "
            "Lütfen bekleyin..."}),
    (r"Could not download the speech recognition model \(no internet\?\)\.",
     {"tr": "Konuşma tanıma modeli indirilemedi (internet bağlantısı yok mu?)."}),
    (r"Could not download the offline translation model \(no internet\?\)\.",
     {"tr": "Çevrimdışı çeviri modeli indirilemedi (internet bağlantısı yok mu?)."}),
    (r"The internet is needed only the first time\. Check it and try again\.",
     {"tr": "İnternet yalnızca ilk seferde gerekir. Bağlantıyı kontrol edip yeniden deneyin."}),
    (r"Speech recognition model downloaded\.",
     {"tr": "Konuşma tanıma modeli indirildi."}),
    (r"Offline translation model downloaded\.",
     {"tr": "Çevrimdışı çeviri modeli indirildi."}),

    # ---------------------------------------------------------------- GPU / CPU (cuda_setup.py)
    (r"Registered (?P<n>\d+) NVIDIA DLL folder\(s\)\.",
     {"tr": "Ekran kartı (GPU) için {n} NVIDIA DLL klasörü hazırlandı."}),
    (r"No pip-installed NVIDIA DLL folders found\.",
     {"tr": "Ekran kartı (GPU) için NVIDIA DLL klasörü bulunamadı."}),
    (r"No CUDA device detected\.",
     {"tr": "Kullanılabilir ekran kartı (NVIDIA GPU) bulunamadı."}),
    (r"CUDA check failed: (?P<detail>.*)",
     {"tr": "Ekran kartı (GPU) denetimi başarısız oldu: {detail}"}),
    (r"CUDA library (?P<dll>\S+) could not be loaded\.",
     {"tr": "Ekran kartı (GPU) kütüphanesi {dll} yüklenemedi."}),

    # ---------------------------------------------------------------- speech recognition
    (r"Loading speech recognition model '(?P<model>[^']+)' on CUDA\.\.\.",
     {"tr": "Konuşma tanıma modeli '{model}' ekran kartına (GPU) yükleniyor..."}),
    (r"Loading speech recognition model '(?P<model>[^']+)' on CPU\.\.\.",
     {"tr": "Konuşma tanıma modeli '{model}' işlemciye (CPU) yükleniyor..."}),
    (r"Transcribing on GPU\.\.\.",
     {"tr": "Konuşmalar yazıya dökülüyor: ekran kartı (GPU) kullanılıyor..."}),
    (r"Transcribing on CPU\.\.\.",
     {"tr": "Konuşmalar yazıya dökülüyor: işlemci (CPU) kullanılıyor..."}),
    (r"Using CPU \(slower\)\.",
     {"tr": "İşlemci (CPU) kullanılacak (daha yavaş)."}),
    # The error text may span several lines: the first and the last line are matched on their own.
    (r"GPU transcription failed \((?P<detail>.*)\)\. Falling back to CPU\.",
     {"tr": "Ekran kartında (GPU) konuşma tanıma başarısız oldu ({detail}). İşlemciyle (CPU) devam ediliyor."}),
    (r"GPU transcription failed \((?P<detail>.*)",
     {"tr": "Ekran kartında (GPU) konuşma tanıma başarısız oldu ({detail}"}),
    (r"(?P<detail>.*)\)\. Falling back to CPU\.",
     {"tr": "{detail}). İşlemciyle (CPU) devam ediliyor."}),
    # "(ValueError: ...)": also matches the first line of a multi-line error (no closing parenthesis).
    (r"Could not load the speech recognition model \((?P<detail>.*)",
     {"tr": "Konuşma tanıma modeli yüklenemedi ({detail}"}),
    (r"Detected language: (?P<lang>\S+) \(probability (?P<p>[\d.]+)\)",
     {"tr": "Algılanan konuşma dili: {lang} (olasılık {p})"}),
    (r"Not sure about the spoken language\. If the subtitles look wrong, choose the spoken "
     r"language instead of Auto-detect\.",
     {"tr": "Konuşulan dil kesin anlaşılamadı. Altyazılar yanlış görünürse “Otomatik algıla” "
            "yerine konuşulan dili seçin."}),
    (r"Skipped unclear sound at " + _TIME + r" \(not speech\?\): (?P<text>.*)",
     {"tr": "{time} anındaki belirsiz ses atlandı (konuşma olmayabilir): {text}"}),
    (r"Skipped subtitle credit at " + _TIME + r" \(not speech\?\): (?P<text>.*)",
     {"tr": "{time} anındaki altyazı imzası atlandı (konuşma olmayabilir): {text}"}),
    (r"Skipped a repeated line at " + _TIME + r": (?P<text>.*)",
     {"tr": "{time} anında tekrarlanan bir satır atlandı: {text}"}),
    (r"No speech was found in this video \(only silence, music or noise\?\)\.",
     {"tr": "Bu videoda konuşma bulunamadı (yalnızca sessizlik, müzik ya da gürültü olabilir)."}),
    (r"Transcription finished: (?P<n>\d+) subtitles\. Saved (?P<name>.+)",
     {"tr": "Konuşma tanıma bitti: {n} altyazı. Kaydedildi: {name}"}),

    # ---------------------------------------------------------------- saving files
    (r"Saved subtitled video: (?P<path>.+)",
     {"tr": "Altyazılı video kaydedildi: {path}"}),
    (r"Saved (?P<name>[^\\/:]+\.(?:srt|vtt))",
     {"tr": "Kaydedildi: {name}"}),
    (r"The previous (?P<name>.+?) was kept as (?P<backup>.+\.bak-\d{8}-\d{6})",
     {"tr": "{name} dosyasının önceki hâli {backup} adıyla saklandı."}),
    (r"Could not save the subtitles \((?P<reason>.+)\)\. Choose another output folder\.",
     {"tr": "Altyazılar kaydedilemedi ({reason}). Başka bir çıktı klasörü seçin."}),

    # ---------------------------------------------------------------- burning
    (r"Burning subtitles into (?P<name>.+) \(re-encoding, this may take a while\)\.\.\.",
     {"tr": "Altyazılar videoya gömülüyor: {name} (video yeniden kodlanıyor, biraz sürebilir)..."}),
    (r"Could not create the subtitled video \(ffmpeg failed\)\.",
     {"tr": "Altyazılı video oluşturulamadı (ffmpeg hata verdi)."}),

    # ---------------------------------------------------------------- translation (translation.py)
    (r"Translating (?P<n>\d+) subtitles \((?P<m>\d+) sentences\), (?P<src>" + _LANG + r") -> "
     r"(?P<tgt>" + _LANG + r")\.",
     {"tr": "{n} altyazı çevriliyor ({m} cümle), {src} → {tgt}."}),
    (r"Translating (?P<n>\d+) long sentence\(s\) again, one subtitle at a time "
     r"\(part of the translation was missing\)\.",
     {"tr": "Çevirisi eksik kalan {n} uzun cümle, her altyazı ayrı ayrı olmak üzere yeniden çevriliyor."}),
    (r"Translating (?P<src>" + _LANG + r") -> (?P<tgt>" + _LANG + r")\.\.\.",
     {"tr": "Çeviri: {src} → {tgt}..."}),
    (r"Unknown translator: (?P<name>.+)",
     {"tr": "Bilinmeyen çevirmen: {name}"}),
    (r"A target language is required\.",
     {"tr": "Bir çeviri dili seçilmesi gerekiyor."}),

    # Online: Google Translate, MyMemory as backup.
    (r"Google Translate is not available \(" + _TOO_MANY + r"\)\. "
     r"Switching to MyMemory \(another online translator\)\.",
     {"tr": f"Çevrimiçi çevirmen (Google) şu an kullanılamıyor ({_TOO_MANY_TR}). "
            "Başka bir çevrimiçi çevirmene (MyMemory) geçiliyor."}),
    (r"Google Translate is not available \(" + _NO_CONNECTION + r"\)\. "
     r"Switching to MyMemory \(another online translator\)\.",
     {"tr": f"Çevrimiçi çevirmen (Google) şu an kullanılamıyor ({_NO_CONNECTION_TR}). "
            "Başka bir çevrimiçi çevirmene (MyMemory) geçiliyor."}),
    (r"Google Translate is not available \((?P<detail>.*)\)\. "
     r"Switching to MyMemory \(another online translator\)\.",
     {"tr": "Çevrimiçi çevirmen (Google) şu an kullanılamıyor ({detail}). "
            "Başka bir çevrimiçi çevirmene (MyMemory) geçiliyor."}),
    (r"Online translation is not available \(" + _TOO_MANY + r"\)\. "
     r"Switching to offline translation \(NLLB\)\.",
     {"tr": f"Çevrimiçi çeviri kullanılamıyor ({_TOO_MANY_TR}). Çevrimdışı çevirmene (NLLB) geçiliyor."}),
    (r"Online translation is not available \(" + _NO_CONNECTION + r"\)\. "
     r"Switching to offline translation \(NLLB\)\.",
     {"tr": f"Çevrimiçi çeviri kullanılamıyor ({_NO_CONNECTION_TR}). Çevrimdışı çevirmene (NLLB) geçiliyor."}),
    (r"Online translation is not available \(" + _DAILY_LIMIT + r"\)\. "
     r"Switching to offline translation \(NLLB\)\.",
     {"tr": f"Çevrimiçi çeviri kullanılamıyor ({_DAILY_LIMIT_TR}). Çevrimdışı çevirmene (NLLB) geçiliyor."}),
    (r"Online translation is not available \((?P<detail>.*)\)\. "
     r"Switching to offline translation \(NLLB\)\.",
     {"tr": "Çevrimiçi çeviri kullanılamıyor ({detail}). Çevrimdışı çevirmene (NLLB) geçiliyor."}),
    (r"Batch (?P<n>\d+): line count mismatch \((?P<got>\d+) vs (?P<want>\d+)\), translating line by line\.",
     {"tr": "{n}. bölümde satır sayısı tutmadı (gelen {got}, beklenen {want}); satırlar tek tek çevriliyor."}),
    (r"Translated batch (?P<n>\d+)/(?P<total>\d+)\.",
     {"tr": "Çevrildi: bölüm {n}/{total}."}),

    # Offline: NLLB.
    (r"Loading offline translation model \(NLLB\) on GPU\.\.\.",
     {"tr": "Çevrimdışı çeviri modeli (NLLB) ekran kartına (GPU) yükleniyor..."}),
    (r"Loading offline translation model \(NLLB\) on CPU\.\.\.",
     {"tr": "Çevrimdışı çeviri modeli (NLLB) işlemciye (CPU) yükleniyor..."}),
    (r"Could not load NLLB on GPU \((?P<detail>.*)\)\. Using CPU\.",
     {"tr": "Çevrimdışı çevirmen (NLLB) ekran kartına (GPU) yüklenemedi ({detail}). "
            "İşlemci (CPU) kullanılıyor."}),
    (r"Could not load NLLB on GPU \((?P<detail>.*)",
     {"tr": "Çevrimdışı çevirmen (NLLB) ekran kartına (GPU) yüklenemedi ({detail}"}),
    (r"(?P<detail>.*)\)\. Using CPU\.",
     {"tr": "{detail}). İşlemci (CPU) kullanılıyor."}),
    (r"Translation on GPU failed \((?P<detail>.*)\)\. Switching to CPU\.",
     {"tr": "Ekran kartında (GPU) çeviri başarısız oldu ({detail}). İşlemciye (CPU) geçiliyor."}),
    (r"Translation on GPU failed \((?P<detail>.*)",
     {"tr": "Ekran kartında (GPU) çeviri başarısız oldu ({detail}"}),
    (r"(?P<detail>.*)\)\. Switching to CPU\.",
     {"tr": "{detail}). İşlemciye (CPU) geçiliyor."}),
    (r"Offline translation does not support the spoken language '(?P<lang>[^']*)'\.",
     {"tr": "Çevrimdışı çevirmen (NLLB) konuşulan dili ('{lang}') desteklemiyor."}),
    (r"If that language is wrong, choose the spoken language instead of Auto-detect; "
     r"otherwise use the online translator\.",
     {"tr": "Bu dil yanlışsa “Otomatik algıla” yerine konuşulan dili seçin; doğruysa "
            "çevrimiçi çevirmeni (Google) kullanın."}),
    (r"Offline translation does not support language '(?P<lang>[^']*)'\.",
     {"tr": "Çevrimdışı çevirmen (NLLB) '{lang}' dilini desteklemiyor."}),
    (r"Use the online translator for this language\.",
     {"tr": "Bu dil için çevrimiçi çevirmeni (Google) kullanın."}),
    (r"Could not load the offline translation model: (?P<detail>.*)",
     {"tr": "Çevrimdışı çeviri modeli yüklenemedi: {detail}"}),
    (r"The offline translator has no language code '(?P<code>[^']*)'\.",
     {"tr": "Çevrimdışı çevirmende '{code}' dil kodu yok."}),
    (r"Offline translation failed: (?P<detail>.*)",
     {"tr": "Çevrimdışı çeviri başarısız oldu: {detail}"}),
]
