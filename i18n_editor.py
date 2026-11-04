"""Texts of the subtitle editor (editor.py), Turkish and English.

Used through i18n.t("ed_..."). All keys start with "ed_" so they never clash with the
main window's table (i18n_app.py). The burn controls (BurnOptions, "ed_burn_*") are
shown in the main window too.

Turkish words used throughout: altyazı (one subtitle), altyazı dosyası (SRT),
Başlangıç / Bitiş / Süre, karakter/sn, Orijinal, Çeviri, gömmek (burn into the video).
"""

STRINGS: dict[str, dict[str, str]] = {
    # ---------------------------------------------------------------- window
    # Same name as the main window's "app_name" (i18n_app.py).
    "ed_app_name": {"tr": "Altyazı Çevirici", "en": "Subtitle Translator"},
    "ed_title": {
        "tr": "{mark}Altyazıları gözden geçir - {name} - {app}",
        "en": "{mark}Review subtitles - {name} - {app}",
    },

    # ---------------------------------------------------------------- cue list
    "ed_col_num": {"tr": "#", "en": "#"},
    "ed_col_start": {"tr": "Başlangıç", "en": "Start"},
    "ed_col_end": {"tr": "Bitiş", "en": "End"},
    "ed_col_original": {"tr": "Orijinal", "en": "Original"},
    "ed_col_translation": {"tr": "Çeviri", "en": "Translation"},
    "ed_flag_count": {
        "tr": "{n} altyazının okunması zor (turuncu satırlar)",
        "en": "{n} cue(s) flagged for readability (highlighted)",
    },
    "ed_flag_none": {
        "tr": "{total} altyazı, okunması zor olan yok",
        "en": "{total} cues, no readability problems",
    },

    # ---------------------------------------------------------------- toolbar
    "ed_btn_previous": {"tr": "◀ Önceki", "en": "◀ Previous"},
    "ed_btn_next": {"tr": "Sonraki ▶", "en": "Next ▶"},
    "ed_btn_play": {"tr": "▶ Oynat (F5)", "en": "▶ Play cue"},
    "ed_btn_split": {"tr": "Ortadan böl", "en": "Split cue at middle"},
    "ed_btn_merge": {"tr": "Sonrakiyle birleştir", "en": "Merge with next"},
    "ed_btn_delete": {"tr": "Sil", "en": "Delete cue"},
    "ed_btn_undo": {"tr": "Geri al", "en": "Undo"},
    "ed_btn_find": {"tr": "Bul ve değiştir…", "en": "Find & replace…"},

    # ---------------------------------------------------------------- details
    "ed_cue": {"tr": "Altyazı", "en": "Cue"},
    "ed_cue_n": {"tr": "Altyazı {n}", "en": "Cue {n}"},
    "ed_start": {"tr": "Başlangıç", "en": "Start"},
    "ed_end": {"tr": "Bitiş", "en": "End"},
    "ed_stats": {
        "tr": "Süre {duration} sn  ·  {chars} karakter  ·  {cps} karakter/sn",
        "en": "{duration} s  ·  {chars} chars  ·  {cps} chars/s",
    },
    "ed_translation": {"tr": "Çeviri", "en": "Translation"},
    "ed_original": {"tr": "Orijinal", "en": "Original"},
    "ed_no_original": {
        "tr": "(orijinal altyazı dosyası yüklenmedi)",
        "en": "(no original subtitles loaded)",
    },

    # ---------------------------------------------------------------- readability
    "ed_issue_end_before_start": {
        "tr": "bitiş, başlangıçtan sonra olmalı",
        "en": "end is not after start",
    },
    "ed_issue_too_long": {
        "tr": "çok uzun: {width} karakterlik {lines} satır gerekiyor",
        "en": "too long: needs {lines} lines of {width} chars",
    },
    "ed_issue_too_fast": {
        "tr": "çok hızlı: {cps} karakter/sn (en çok {max})",
        "en": "too fast: {cps} chars/s (max {max})",
    },
    "ed_issue_empty": {"tr": "boş", "en": "empty"},
    "ed_issue_overlap": {
        "tr": "sonraki altyazıyla çakışıyor",
        "en": "overlaps the next cue",
    },
    "ed_issue_sep": {"tr": "; ", "en": "; "},

    # ---------------------------------------------------------------- times
    "ed_time_invalid": {
        "tr": "“{text}” geçerli bir zaman değil: 00:01:23,450 biçiminde yazın",
        "en": "“{text}” is not a valid time - write it like 00:01:23,450",
    },
    "ed_time_end_before_start": {
        "tr": "Bitiş, başlangıçtan sonra olmalı.",
        "en": "End must be after start.",
    },
    "ed_time_reset": {
        "tr": "⚠ {error}  (eski zamanlar geri yüklendi)",
        "en": "⚠ {error}  (times reset)",
    },

    # ---------------------------------------------------------------- cue operations
    "ed_split_one_word": {
        "tr": "Bu altyazıda tek kelime var, bölünecek bir şey yok.",
        "en": "This cue has only one word - nothing to split.",
    },
    "ed_merge_last": {
        "tr": "Bu son altyazı: birleştirilecek sonraki altyazı yok.",
        "en": "This is the last cue: there is no next cue to merge with.",
    },
    "ed_nothing_to_undo": {"tr": "Geri alınacak bir şey yok.", "en": "Nothing to undo."},

    # ---------------------------------------------------------------- frame preview
    "ed_video_not_found_short": {"tr": "Video dosyası bulunamadı", "en": "Video file not found"},
    "ed_loading_frame": {"tr": "Görüntü yükleniyor…", "en": "Loading frame…"},
    "ed_no_preview": {"tr": "Önizleme yok", "en": "No preview"},
    "ed_no_picture": {
        "tr": "Bu an için görüntü alınamadı.",
        "en": "No picture available for this moment.",
    },
    "ed_frame_failed_log": {
        "tr": "Önizleme görüntüsü alınamadı ({time}): {error}",
        "en": "Frame preview failed at {time}: {error}",
    },
    "ed_ffmpeg_failed": {"tr": "ffmpeg çalışmadı", "en": "ffmpeg failed"},
    "ed_ffmpeg_missing": {
        "tr": "FFmpeg kurulu değil. setup.bat dosyasını yeniden çalıştırın.",
        "en": "FFmpeg is not installed. Run setup.bat again.",
    },

    # ---------------------------------------------------------------- playback
    "ed_video_not_found": {"tr": "Video dosyası bulunamadı.", "en": "Video file not found."},
    "ed_player_title": {"tr": "Altyazı {n}: {text}", "en": "Cue {n}: {text}"},
    "ed_ffplay_missing": {
        "tr": "Video oynatılamıyor: ffplay (FFmpeg'in bir parçası) kurulu değil. "
              "setup.bat dosyasını yeniden çalıştırın.",
        "en": "Cannot play the video: ffplay (part of FFmpeg) is not installed. "
              "Run setup.bat again.",
    },

    # ---------------------------------------------------------------- save / burn
    "ed_burn_frame": {"tr": "Kaydetme ve videoya gömme", "en": "Save and burn"},
    "ed_btn_save": {"tr": "Kaydet (Ctrl+S)", "en": "Save  (Ctrl+S)"},
    "ed_btn_burn": {"tr": "Kaydet ve videoya göm", "en": "Save & burn video"},
    "ed_btn_cancel": {"tr": "İptal", "en": "Cancel"},
    "ed_btn_open_folder": {"tr": "Klasörü aç", "en": "Open folder"},
    "ed_no_permission": {
        "tr": "İzin yok ya da dosya başka bir programda açık.",
        "en": "No permission, or the file is open in another program.",
    },
    "ed_save_failed": {
        "tr": "Altyazılar kaydedilemedi:\n{path}\n\n{reason}",
        "en": "Could not save the subtitles:\n{path}\n\n{reason}",
    },
    "ed_saved": {"tr": "Kaydedildi: {name}", "en": "Saved {name}"},
    "ed_video_not_found_path": {
        "tr": "Video dosyası bulunamadı:\n{path}",
        "en": "Video file not found:\n{path}",
    },
    "ed_engine_failed": {
        "tr": "İşlem motoru yüklenemedi:\n{error}",
        "en": "Cannot load the processing engine:\n{error}",
    },
    "ed_burning": {
        "tr": "Altyazılar videoya gömülüyor…",
        "en": "Burning subtitles into the video…",
    },
    "ed_cancelling": {"tr": "İptal ediliyor…", "en": "Cancelling…"},
    "ed_burn_cancelled": {"tr": "Gömme işlemi iptal edildi.", "en": "Burning cancelled."},
    "ed_burn_failed_status": {
        "tr": "Altyazılar videoya gömülemedi.",
        "en": "Burning failed.",
    },
    "ed_burn_failed": {
        "tr": "Altyazılı video oluşturulamadı.",
        "en": "The video with subtitles could not be created.",
    },
    "ed_burn_failed_saved": {
        "tr": "Altyazılarınız kaydedildi.",
        "en": "Your subtitles are saved.",
    },
    "ed_burn_failed_log": {
        "tr": "Ayrıntılar ana penceredeki kayıt alanında.",
        "en": "Details are in the log of the main window.",
    },
    "ed_video_saved_status": {"tr": "Video kaydedildi: {path}", "en": "Video saved: {path}"},
    "ed_video_saved": {
        "tr": "Altyazılı video kaydedildi:\n{path}\n\nKlasör açılsın mı?",
        "en": "Video with subtitles saved:\n{path}\n\nOpen the folder?",
    },
    "ed_open_folder_failed": {
        "tr": "Klasör açılamadı:\n{error}",
        "en": "Cannot open folder:\n{error}",
    },

    # ---------------------------------------------------------------- transcript export
    # (the dialog is also opened from the main window: File > Make a transcript…)
    "ed_btn_transcript": {
        "tr": "Metin dökümü olarak dışa aktar…",
        "en": "Export as transcript…",
    },
    "ed_transcript_title": {"tr": "Metin dökümü olarak dışa aktar", "en": "Export as transcript"},
    "ed_transcript_from": {"tr": "Altyazı dosyası: {name}", "en": "Subtitles: {name}"},
    "ed_transcript_format": {"tr": "Biçim:", "en": "Format:"},
    "ed_transcript_docx": {"tr": "Word belgesi (.docx)", "en": "Word document (.docx)"},
    "ed_transcript_txt": {"tr": "Düz metin (.txt)", "en": "Plain text (.txt)"},
    "ed_transcript_timestamps": {
        "tr": "Zaman damgalarını ekle, ör. [00:01:23]",
        "en": "Include timestamps, e.g. [00:01:23]",
    },
    "ed_transcript_saved_first": {
        "tr": "Kaydedilmemiş değişiklikler önce kaydedilir.",
        "en": "Unsaved changes are saved first.",
    },
    "ed_transcript_save": {"tr": "Kaydet…", "en": "Save…"},
    "ed_transcript_save_as": {"tr": "Metin dökümünü kaydet", "en": "Save the transcript"},
    "ed_docx_files": {"tr": "Word belgeleri", "en": "Word documents"},
    "ed_txt_files": {"tr": "Metin dosyaları", "en": "Text files"},
    "ed_transcript_done_status": {
        "tr": "Metin dökümü kaydedildi: {name}",
        "en": "Transcript saved: {name}",
    },
    "ed_transcript_done": {
        "tr": "Metin dökümü kaydedildi:\n{path}\n\nŞimdi açılsın mı?",
        "en": "Transcript saved:\n{path}\n\nOpen it now?",
    },
    "ed_transcript_failed": {
        "tr": "Metin dökümü oluşturulamadı.\n\n{reason}",
        "en": "The transcript could not be created.\n\n{reason}",
    },
    "ed_transcript_missing": {
        "tr": "Metin dökümü bölümü (transcript.py) yüklenemedi: {error}",
        "en": "The transcript module (transcript.py) could not be loaded: {error}",
    },
    "ed_file_open_failed": {
        "tr": "Dosya açılamadı:\n{error}",
        "en": "Cannot open the file:\n{error}",
    },

    # ---------------------------------------------------------------- burn options
    # (also used in the main window, under "Video with subtitles")
    "ed_burn_position": {"tr": "Konum:", "en": "Position:"},
    "ed_burn_size": {"tr": "Boyut:", "en": "Size:"},
    "ed_burn_font": {"tr": "Yazı tipi:", "en": "Font:"},
    "ed_burn_box": {"tr": "Arka plan kutusu", "en": "Background box"},
    "ed_burn_position_bottom": {"tr": "Alt", "en": "Bottom"},
    "ed_burn_position_top": {"tr": "Üst", "en": "Top"},
    "ed_burn_size_auto": {"tr": "Otomatik", "en": "Auto"},
    "ed_burn_size_small": {"tr": "Küçük", "en": "Small"},
    "ed_burn_size_medium": {"tr": "Orta", "en": "Medium"},
    "ed_burn_size_large": {"tr": "Büyük", "en": "Large"},

    # ---------------------------------------------------------------- closing
    "ed_close_while_burning": {
        "tr": "Bir video hâlâ oluşturuluyor. Durdurup pencereyi kapatmak istiyor musunuz?",
        "en": "A video is still being created. Stop it and close?",
    },
    "ed_save_changes": {
        "tr": "Altyazılarda yaptığınız değişiklikler kaydedilsin mi?",
        "en": "Save your changes to the subtitles?",
    },

    # ---------------------------------------------------------------- find & replace
    "ed_find_title": {"tr": "Bul ve değiştir", "en": "Find & replace"},
    "ed_find_label": {"tr": "Aranan:", "en": "Find:"},
    "ed_replace_label": {"tr": "Yerine yazılacak:", "en": "Replace with:"},
    "ed_match_case": {"tr": "Büyük/küçük harf duyarlı", "en": "Match case"},
    "ed_find_next": {"tr": "Sonrakini bul", "en": "Find next"},
    "ed_replace": {"tr": "Değiştir", "en": "Replace"},
    "ed_replace_all": {"tr": "Tümünü değiştir", "en": "Replace all"},
    "ed_close": {"tr": "Kapat", "en": "Close"},
    "ed_not_found": {"tr": "Bulunamadı.", "en": "Not found."},
    "ed_no_more_matches": {"tr": "Başka eşleşme yok.", "en": "No more matches."},
    "ed_replaced": {
        "tr": "{cues} altyazıda {total} yer değiştirildi.",
        "en": "Replaced {total} occurrence(s) in {cues} cue(s).",
    },

    # ---------------------------------------------------------------- standalone start
    "ed_choose_video": {"tr": "Videoyu seçin", "en": "Choose the video"},
    "ed_video_files": {"tr": "Video dosyaları", "en": "Video files"},
    "ed_all_files": {"tr": "Tüm dosyalar", "en": "All files"},
    "ed_choose_srt": {
        "tr": "Düzenlenecek altyazı dosyasını seçin",
        "en": "Choose the subtitles to edit",
    },
    "ed_srt_files": {"tr": "Altyazı dosyaları (SRT)", "en": "SubRip subtitles"},
    "ed_open_failed": {
        "tr": "Altyazı dosyası açılamadı:\n{error}",
        "en": "Cannot open the subtitles:\n{error}",
    },
    "ed_subtitles_module_failed": {
        "tr": "subtitles.py yüklenemedi:\n{details}",
        "en": "subtitles.py could not be loaded:\n{details}",
    },
}
