"""Texts of the main window (app.py) in Turkish and English. See i18n.py.

Keys are grouped by where they appear. Placeholders in {braces} must be the same in
both languages (tests check this).
"""

STRINGS: dict[str, dict[str, str]] = {
    # ------------------------------------------------------------ window, menus
    "app_name": {"tr": "Altyazı Çevirici", "en": "Subtitle Translator"},
    "menu_file": {"tr": "Dosya", "en": "File"},
    "menu_add_videos": {"tr": "Video ekle…", "en": "Add videos…"},
    "menu_add_folder": {"tr": "Klasör ekle…", "en": "Add folder…"},
    "menu_open_subtitles": {"tr": "Altyazı dosyası aç…", "en": "Open subtitles…"},
    "menu_make_transcript": {
        "tr": "Altyazıdan metin dökümü oluştur…",
        "en": "Make a transcript from subtitles…",
    },
    "dlg_choose_srt": {
        "tr": "Metin dökümü oluşturulacak altyazı dosyasını seçin",
        "en": "Choose the subtitles to make a transcript from",
    },
    "menu_exit": {"tr": "Çıkış", "en": "Exit"},
    "menu_settings": {"tr": "Ayarlar", "en": "Settings"},
    "menu_language": {"tr": "Dil", "en": "Language"},
    "menu_edit_glossary": {"tr": "Sözlüğü düzenle…", "en": "Edit glossary…"},
    "menu_help": {"tr": "Yardım", "en": "Help"},
    "menu_user_guide": {"tr": "Kullanım kılavuzu", "en": "User guide"},
    "menu_about": {"tr": "Hakkında", "en": "About"},
    "about_title": {"tr": "Hakkında", "en": "About"},
    "about_text": {
        "tr": "Altyazı Çevirici\n\n"
              "Videolardaki konuşmayı yazıya döker, altyazıları istediğiniz dillere çevirir; "
              "isterseniz altyazıları gözden geçirip yeni bir videoya gömer.\n\n"
              "DİLGEM eğitim videoları için hazırlanmıştır.",
        "en": "Subtitle Translator\n\n"
              "Writes subtitles for the speech in your videos, translates them into the "
              "languages you choose and, if you like, lets you review them and burn them "
              "into a new video.\n\n"
              "Made for the training videos of DİLGEM.",
    },
    "guide_missing": {
        "tr": "Kullanım kılavuzu bulunamadı:\n{path}",
        "en": "The user guide was not found:\n{path}",
    },
    "guide_open_failed": {
        "tr": "Kullanım kılavuzu açılamadı:\n{error}",
        "en": "Cannot open the user guide:\n{error}",
    },
    "language_later": {
        "tr": "Videolar işlenirken dil değiştirilemiyor.\n"
              "Seçtiğiniz dil, işlem bittiğinde uygulanacak.",
        "en": "The language cannot change while videos are being processed.\n"
              "Your choice will be applied when the work has finished.",
    },

    # ------------------------------------------------------------ video list
    "frame_videos": {"tr": "Video listesi", "en": "Videos"},
    "col_file": {"tr": "Dosya", "en": "File"},
    "col_status": {"tr": "Durum", "en": "Status"},
    "col_result": {"tr": "Diller / Sonuç", "en": "Languages / Result"},
    "btn_add_videos": {"tr": "Video ekle…", "en": "Add videos…"},
    "btn_add_folder": {"tr": "Klasör ekle…", "en": "Add folder…"},
    "btn_remove": {"tr": "Kaldır", "en": "Remove"},
    "btn_clear_finished": {"tr": "Bitenleri temizle", "en": "Clear finished"},
    "btn_open_subtitles": {"tr": "Altyazı dosyası aç…", "en": "Open subtitles…"},
    "btn_review": {"tr": "Gözden geçir / düzenle…", "en": "Review / edit…"},
    "hint_drop": {
        "tr": "Videoları veya klasörleri buraya sürükleyip bırakın\n"
              "ya da “Video ekle…” düğmesine tıklayın",
        "en": "Drag & drop videos or folders here\nor click “Add videos…”",
    },
    "hint_click_add": {
        "tr": "Başlamak için “Video ekle…” düğmesine tıklayın",
        "en": "Click “Add videos…” to start",
    },

    # statuses (Status column)
    "status_waiting": {"tr": "Bekliyor", "en": "Waiting"},
    "status_working": {"tr": "Çalışıyor %{pct}", "en": "Working {pct}%"},
    "status_done": {"tr": "Tamamlandı", "en": "Done"},
    "status_review": {"tr": "Gözden geçirmeye hazır", "en": "Ready for review"},
    "status_failed": {"tr": "Başarısız", "en": "Failed"},
    "status_cancelled": {"tr": "İptal edildi", "en": "Cancelled"},
    # batch summary counts ("2 done, 1 failed")
    "count_done": {"tr": "{n} tamamlandı", "en": "{n} done"},
    "count_review": {"tr": "{n} gözden geçirmeye hazır", "en": "{n} ready for review"},
    "count_failed": {"tr": "{n} başarısız", "en": "{n} failed"},
    "count_cancelled": {"tr": "{n} iptal edildi", "en": "{n} cancelled"},
    "nothing_processed": {"tr": "hiçbir video işlenmedi", "en": "nothing processed"},
    "result_one_video": {"tr": "1 video", "en": "1 video"},
    "result_n_videos": {"tr": "{n} video", "en": "{n} videos"},
    "result_transcripts": {"tr": "metin dökümü: {formats}", "en": "transcript: {formats}"},
    "fmt_docx": {"tr": "Word", "en": "Word"},
    "fmt_txt": {"tr": "Metin", "en": "Text"},
    "fmt_md": {"tr": "Markdown", "en": "Markdown"},
    # time left (status line, Status column)
    "status_working_eta": {"tr": "Çalışıyor %{pct} · {eta}", "en": "Working {pct}% · {eta}"},
    "eta_left": {"tr": "yaklaşık {time} kaldı", "en": "about {time} left"},
    "eta_less_minute": {"tr": "1 dakikadan az kaldı", "en": "less than a minute left"},
    "eta_short": {"tr": "~{time}", "en": "~{time}"},
    "eta_short_less": {"tr": "<1 dk", "en": "<1 min"},
    "eta_min": {"tr": "{n} dk", "en": "{n} min"},
    "eta_hours": {"tr": "{h} sa", "en": "{h} h"},
    "eta_hours_min": {"tr": "{h} sa {m} dk", "en": "{h} h {m} min"},
    "eta_batch": {"tr": "Tüm videolar: {eta}", "en": "All videos: {eta}"},

    # ------------------------------------------------------------ settings
    "frame_settings": {"tr": "Ayarlar", "en": "Settings"},
    "label_source": {"tr": "Kaynak dil (konuşulan dil):", "en": "Source language:"},
    "auto_detect": {"tr": "Otomatik algıla", "en": "Auto-detect"},
    "label_model": {"tr": "Model:", "en": "Model:"},
    "hint_model": {"tr": "büyük = daha doğru, daha yavaş", "en": "bigger = more accurate, slower"},
    "label_translator": {"tr": "Çevirmen:", "en": "Translator:"},
    "translator_nllb": {
        "tr": "Çevrimdışı – NLLB (en iyi, gizli, sınırsız)",
        "en": "Offline – NLLB (best, private, no limits)",
    },
    "translator_nllb_large": {
        "tr": "Çevrimdışı – NLLB büyük model (en iyi kalite, daha yavaş)",
        "en": "Offline – NLLB large model (best quality, slower)",
    },
    "translator_online": {
        "tr": "Çevrimiçi – Google Translate",
        "en": "Online – Google Translate",
    },
    # options under the settings ("Advanced" is folded away until opened)
    "check_clean_audio": {
        "tr": "Konuşmayı temizle (yankılı/gürültülü salonlar için)",
        "en": "Clean up the speech (for echoing/noisy halls)",
    },
    "hint_clean_audio": {"tr": "işlem biraz uzar", "en": "takes a little longer"},
    "label_export": {"tr": "Metin dökümünü de kaydet:", "en": "Also save a transcript:"},
    "check_export_docx": {"tr": "Word", "en": "Word"},
    "check_export_txt": {"tr": "Metin", "en": "Text"},
    "btn_advanced": {"tr": "Gelişmiş", "en": "Advanced"},
    "check_retime": {
        "tr": "Çevirileri tam cümle olarak zamanla",
        "en": "Time translations as whole sentences",
    },
    "hint_retime": {
        "tr": "(kapalıysa çeviriler orijinal altyazıların zamanlarını kullanır)",
        "en": "(off: translations keep the timing of the original subtitles)",
    },
    "label_output": {"tr": "Çıktı klasörü:", "en": "Output folder:"},
    "btn_browse": {"tr": "Gözat…", "en": "Browse…"},
    "hint_output": {
        "tr": "(isteğe bağlı – boş bırakılırsa her videonun yanına)",
        "en": "(optional - empty = next to each video)",
    },
    "label_targets": {
        "tr": "Hedef diller (birden fazla seçmek için tıklayın):",
        "en": "Target languages (click to select several):",
    },
    "targets_none": {"tr": "Hedef dil seçilmedi", "en": "No target language selected"},
    "targets_selected": {"tr": "{n} seçili: {names}", "en": "{n} selected: {names}"},
    "targets_more": {"tr": " +{n} daha", "en": " +{n} more"},

    # ------------------------------------------------------------ burning
    "frame_burn": {"tr": "Altyazılı video", "en": "Video with subtitles"},
    "check_burn": {"tr": "Altyazıları yeni bir videoya göm", "en": "Burn subtitles into a new video"},
    "check_review": {
        "tr": "Videoya gömmeden önce altyazıları gözden geçir",
        "en": "Review subtitles before burning",
    },

    # ------------------------------------------------------------ actions, status line
    "btn_start": {"tr": "▶ Başlat", "en": "▶ Start"},
    "btn_cancel": {"tr": "İptal", "en": "Cancel"},
    "btn_edit_glossary": {"tr": "Sözlüğü düzenle…", "en": "Edit glossary…"},
    "btn_open_output": {"tr": "Çıktı klasörünü aç", "en": "Open output folder"},
    "check_shutdown": {"tr": "İş bitince bilgisayarı kapat", "en": "Shut down the PC when finished"},
    "status_ready": {"tr": "Hazır", "en": "Ready"},
    "status_starting": {"tr": "Başlıyor…", "en": "Starting…"},
    "status_cancelling": {"tr": "İptal ediliyor…", "en": "Cancelling…"},
    "status_stopping": {"tr": "Durduruluyor, lütfen bekleyin…", "en": "Stopping, please wait…"},
    "status_video": {"tr": "Video {n}/{total}", "en": "Video {n} of {total}"},
    "status_finished": {"tr": "Bitti: {summary}", "en": "Finished: {summary}"},
    "status_batch_cancelled": {"tr": "İptal edildi: {summary}", "en": "Cancelled: {summary}"},
    "elapsed_min": {"tr": "{n} dk geçti", "en": "{n} min so far"},
    "elapsed_sec": {"tr": "{n} sn geçti", "en": "{n} s so far"},

    # current step of the running video (status line)
    "phase_starting": {"tr": "Başlıyor", "en": "Starting"},
    "phase_audio": {"tr": "Videonun sesi okunuyor", "en": "Reading the sound of the video"},
    "phase_download_whisper": {
        "tr": "Konuşma tanıma modeli indiriliyor (yalnızca ilk sefer)",
        "en": "Downloading the speech recognition model (only the first time)",
    },
    "phase_load_whisper": {
        "tr": "Konuşma tanıma modeli yükleniyor",
        "en": "Loading the speech recognition model",
    },
    "phase_transcribe": {
        "tr": "Konuşma dinlenip altyazılar yazılıyor",
        "en": "Listening and writing the subtitles",
    },
    "phase_translate_into": {"tr": "Çevriliyor: {lang}", "en": "Translating into {lang}"},
    "phase_download_nllb": {
        "tr": "Çeviri modeli indiriliyor (yalnızca ilk sefer)",
        "en": "Downloading the translation model (only the first time)",
    },
    "phase_load_nllb": {"tr": "Çeviri modeli yükleniyor", "en": "Loading the translation model"},
    "phase_burn": {"tr": "Altyazılı video hazırlanıyor", "en": "Making the video with subtitles"},
    "phase_clean_audio": {
        "tr": "Videonun sesi okunup konuşma temizleniyor",
        "en": "Reading the sound and cleaning up the speech",
    },

    # ------------------------------------------------------------ log lines
    "log_engine_failed": {
        "tr": "İşlem motoru (engine.py) yüklenemedi:\n{details}",
        "en": "Failed to load engine.py:\n{details}",
    },
    "log_dnd_unavailable": {
        "tr": "Sürükle-bırak kullanılamıyor: {error}",
        "en": "Drag & drop unavailable: {error}",
    },
    "log_added": {"tr": "{n} video eklendi.", "en": "Added {n} video(s)."},
    "log_batch_start": {
        "tr": "=== Başlıyor: {n} video → {langs}",
        "en": "=== Starting batch: {n} video(s) -> {langs}",
    },
    "log_cancel_requested": {
        "tr": "İptal istendi, geçerli adım bitince durulacak…",
        "en": "Cancel requested, stopping after the current step…",
    },
    "log_detected": {"tr": "  Algılanan dil: {lang}", "en": "  Detected language: {lang}"},
    "log_original_srt": {"tr": "  Orijinal altyazılar: {path}", "en": "  Original subtitles: {path}"},
    "log_srt": {"tr": "  Altyazılar ({lang}): {path}", "en": "  Subtitles ({lang}): {path}"},
    "log_video": {"tr": "  Video ({lang}): {path}", "en": "  Video ({lang}): {path}"},
    "log_failed": {
        "tr": "  Başarısız: {reason}\n  Teknik ayrıntılar (destek için):\n{details}",
        "en": "  Failed: {reason}\n  Technical details (for support):\n{details}",
    },
    "log_batch_finished": {"tr": "=== İş bitti: {summary}", "en": "=== Batch finished: {summary}"},
    "log_batch_cancelled": {
        "tr": "=== İş iptal edildi: {summary}",
        "en": "=== Batch cancelled: {summary}",
    },
    "log_review_hint": {
        "tr": "Altyazıları kontrol edip videoyu oluşturmak için “Gözden geçirmeye hazır” "
              "yazan videoya çift tıklayın.",
        "en": "Double-click a video marked “Ready for review” to check its subtitles and "
              "burn the video.",
    },
    "log_burned": {"tr": "Altyazılı video kaydedildi: {path}", "en": "Video with subtitles saved: {path}"},
    "log_transcript": {"tr": "  Metin dökümü ({lang}): {path}", "en": "  Transcript ({lang}): {path}"},
    "log_transcript_saved": {"tr": "Metin dökümü kaydedildi: {path}", "en": "Transcript saved: {path}"},
    "log_option_unsupported": {
        "tr": "Not: işlem motorunun bu sürümü şu seçenekleri desteklemiyor, yok sayıldı: {options}",
        "en": "Note: this version of the engine does not support these options, ignored: {options}",
    },
    "log_saved_log": {"tr": "Kayıt dosyası: {path}", "en": "Log saved: {path}"},
    "log_shutdown": {"tr": "Bilgisayar kapatılıyor…", "en": "Shutting down the PC…"},
    "log_shutdown_cancelled": {
        "tr": "Bilgisayarın kapatılması iptal edildi.",
        "en": "Shutting down the PC was cancelled.",
    },

    # ------------------------------------------------------------ popups
    "engine_missing": {
        "tr": "İşlem motoru yüklenemedi.\nAyrıntılar alttaki kayıt alanında.",
        "en": "Could not load the processing engine.\nSee the log for details.",
    },
    "note_not_videos": {
        "tr": "Bunlar video dosyası olmadığı için eklenmedi:\n{names}",
        "en": "These are not video files, so they were not added:\n{names}",
    },
    "and_more": {"tr": "\n… ve {n} tane daha", "en": "\n… and {n} more"},
    "note_duplicates": {"tr": "Bu videolar zaten listede.", "en": "These videos are already in the list."},
    "note_no_videos": {"tr": "Bu klasörde video bulunamadı.", "en": "No videos were found in this folder."},
    "note_supported": {
        "tr": "Desteklenen video türleri: {types}.",
        "en": "Supported video types: {types}.",
    },
    "remove_running": {
        "tr": "Bu video şu anda işleniyor, bu yüzden listede kalıyor.\n"
              "Durdurmak için önce İptal'e basın.",
        "en": "This video is being processed right now, so it stays in the list.\n"
              "Press Cancel first to stop it.",
    },
    "glossary_failed": {"tr": "Sözlük açılamadı.\n\n{reason}", "en": "Cannot open the glossary.\n\n{reason}"},
    "glossary_new_file": {
        "tr": "# Olduğu gibi kalacak terimler, her satıra bir tane\n",
        "en": "# Terms kept exactly as written, one per line\n",
    },
    "folder_open_failed": {"tr": "Klasör açılamadı:\n{error}", "en": "Cannot open folder:\n{error}"},
    "no_output_folder": {
        "tr": "Henüz çıktı klasörü yok – önce bir video işleyin.",
        "en": "No output folder yet - process a video first.",
    },
    "no_subtitles_yet": {
        "tr": "Bu videonun henüz altyazısı yok.\nÖnce Başlat'a basarak videoyu işleyin.",
        "en": "This video has no subtitles yet.\nPress Start to process it first.",
    },
    "srt_not_found": {"tr": "Altyazı dosyası bulunamadı:\n{path}", "en": "Subtitle file not found:\n{path}"},
    "editor_failed": {
        "tr": "Bu altyazılar düzenleyicide açılamadı.\n\n{reason}",
        "en": "Cannot open these subtitles in the editor.\n\n{reason}",
    },
    "need_target": {
        "tr": "Lütfen en az bir hedef dil seçin.",
        "en": "Please select at least one target language.",
    },
    "nothing_waiting": {
        "tr": "Listede bekleyen video yok.\nÖnce video ekleyin (ya da videoları pencereye sürükleyin).",
        "en": "There are no videos waiting in the list.\nAdd videos first (or drag them onto the window).",
    },
    "bad_output_folder": {
        "tr": "Çıktı klasörü kullanılamıyor:\n{folder}\n\n{problem}\n\n"
              "Başka bir klasör seçin ya da her videonun yanına kaydetmek için boş bırakın.",
        "en": "The output folder cannot be used:\n{folder}\n\n{problem}\n\n"
              "Choose another folder, or leave it empty to save next to each video.",
    },
    "batch_failures": {
        "tr": "{n} video işlenemedi:\n\n{lines}\n\n"
              "Tekrar denemek için Başlat'a basın. Ayrıntılar alttaki kayıt alanında.",
        "en": "{n} video(s) could not be processed:\n\n{lines}\n\n"
              "Press Start to try them again. Details are in the log.",
    },
    "shutdown_title": {"tr": "Bilgisayar kapatılacak", "en": "The PC will shut down"},
    "shutdown_text": {
        "tr": "İş bitti: {summary}.\n\nBilgisayar {n} saniye içinde kapatılacak.",
        "en": "Finished: {summary}.\n\nThe PC will shut down in {n} seconds.",
    },
    "shutdown_now": {"tr": "Şimdi kapat", "en": "Shut down now"},
    "shutdown_failed": {
        "tr": "Bilgisayar kapatılamadı:\n{error}",
        "en": "Could not shut down the PC:\n{error}",
    },
    "quit_running": {
        "tr": "Videolar hâlâ işleniyor.\nDurdurup çıkılsın mı?",
        "en": "Videos are still being processed.\nStop and quit?",
    },

    # ------------------------------------------------------------ errors (friendly_error, folder_problem)
    "err_permission": {
        "tr": "Dosyalar oraya kaydedilemiyor: izin yok ya da bir dosya başka bir programda açık.",
        "en": "Cannot save the files there: no permission, or a file is open in another program.",
    },
    "err_disk_full": {
        "tr": "Disk dolu. Biraz yer açıp tekrar deneyin.",
        "en": "The disk is full. Free some space and try again.",
    },
    "err_memory": {
        "tr": "Bellek yetersiz. Diğer programları kapatın ya da daha küçük bir model seçin.",
        "en": "Not enough memory. Close other programs or choose a smaller model.",
    },
    "err_unexpected": {
        "tr": "Beklenmeyen hata ({name}). Ayrıntılar alttaki kayıt alanında.",
        "en": "Unexpected error ({name}). Details are in the log below.",
    },
    "err_not_a_folder": {"tr": "Bu bir dosya, klasör değil.", "en": "This is a file, not a folder."},

    # ------------------------------------------------------------ file dialogs
    "dlg_add_videos": {"tr": "Video ekle", "en": "Add videos"},
    "dlg_add_folder": {"tr": "Bir klasördeki tüm videoları ekle", "en": "Add all videos in a folder"},
    "dlg_output_folder": {"tr": "Çıktı klasörünü seçin", "en": "Choose output folder"},
    "dlg_choose_file": {"tr": "Dosya seçin", "en": "Choose file"},
    "filter_videos": {"tr": "Video dosyaları", "en": "Video files"},
    "filter_srt": {"tr": "Altyazı dosyaları (SRT)", "en": "SubRip subtitles"},
    "filter_all": {"tr": "Tüm dosyalar", "en": "All files"},

    # ------------------------------------------------------------ "Open subtitles" dialog
    "open_title": {"tr": "Altyazı dosyası aç", "en": "Open subtitles"},
    "open_video": {"tr": "Video:", "en": "Video:"},
    "open_srt": {"tr": "Düzenlenecek altyazı dosyası:", "en": "Subtitles to edit:"},
    "open_original": {
        "tr": "Orijinal altyazı dosyası\n(isteğe bağlı):",
        "en": "Original subtitles\n(optional):",
    },
    "open_editor": {"tr": "Düzenleyiciyi aç", "en": "Open editor"},
    "open_need_video": {
        "tr": "Lütfen var olan bir video dosyası seçin.",
        "en": "Please choose an existing video file.",
    },
    "open_need_srt": {
        "tr": "Lütfen düzenlenecek altyazı dosyasını (.srt) seçin.",
        "en": "Please choose the subtitle (.srt) file to edit.",
    },

    # ------------------------------------------------------------ language names (engine.LANGUAGES codes)
    "lang_tr": {"tr": "Türkçe", "en": "Turkish"},
    "lang_en": {"tr": "İngilizce", "en": "English"},
    "lang_de": {"tr": "Almanca", "en": "German"},
    "lang_fr": {"tr": "Fransızca", "en": "French"},
    "lang_es": {"tr": "İspanyolca", "en": "Spanish"},
    "lang_it": {"tr": "İtalyanca", "en": "Italian"},
    "lang_pt": {"tr": "Portekizce", "en": "Portuguese"},
    "lang_nl": {"tr": "Felemenkçe", "en": "Dutch"},
    "lang_ru": {"tr": "Rusça", "en": "Russian"},
    "lang_uk": {"tr": "Ukraynaca", "en": "Ukrainian"},
    "lang_pl": {"tr": "Lehçe", "en": "Polish"},
    "lang_cs": {"tr": "Çekçe", "en": "Czech"},
    "lang_ro": {"tr": "Rumence", "en": "Romanian"},
    "lang_hu": {"tr": "Macarca", "en": "Hungarian"},
    "lang_el": {"tr": "Yunanca", "en": "Greek"},
    "lang_bg": {"tr": "Bulgarca", "en": "Bulgarian"},
    "lang_sv": {"tr": "İsveççe", "en": "Swedish"},
    "lang_no": {"tr": "Norveççe", "en": "Norwegian"},
    "lang_da": {"tr": "Danca", "en": "Danish"},
    "lang_fi": {"tr": "Fince", "en": "Finnish"},
    "lang_ar": {"tr": "Arapça", "en": "Arabic"},
    "lang_fa": {"tr": "Farsça", "en": "Persian"},
    "lang_he": {"tr": "İbranice", "en": "Hebrew"},
    "lang_hi": {"tr": "Hintçe", "en": "Hindi"},
    "lang_ur": {"tr": "Urduca", "en": "Urdu"},
    "lang_bn": {"tr": "Bengalce", "en": "Bengali"},
    "lang_zh": {"tr": "Çince", "en": "Chinese"},
    "lang_ja": {"tr": "Japonca", "en": "Japanese"},
    "lang_ko": {"tr": "Korece", "en": "Korean"},
    "lang_id": {"tr": "Endonezce", "en": "Indonesian"},
    "lang_ms": {"tr": "Malayca", "en": "Malay"},
    "lang_vi": {"tr": "Vietnamca", "en": "Vietnamese"},
    "lang_th": {"tr": "Tayca", "en": "Thai"},
    "lang_az": {"tr": "Azerbaycan Türkçesi", "en": "Azerbaijani"},
    "lang_kk": {"tr": "Kazakça", "en": "Kazakh"},
}
