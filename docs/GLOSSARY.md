# The DİLGEM glossary: how it was built

`glossary.example.txt` is the glossary the program ships with: about 4,600 English → Turkish
and 3,600 Turkish → English terms, plus about 230 names, methods and tests kept as written.
This page explains where the terms come from, which choices were made, and how they were tested.
Every researched term (about 5,600 rows), with its Turkish alternatives and source links, is in
[glossary_sources.tsv](glossary_sources.tsv).

Fields covered: play therapy; autism and developmental interventions; speech and language
therapy (language, speech sound disorders, motor speech, stuttering and cluttering, voice and
resonance, swallowing and feeding incl. IDDSI, hearing, AAC); occupational therapy (Ayres
sensory integration, praxis, fine motor and handwriting, OT models, ADL); physiotherapy
(paediatric neurology and orthopaedics, cerebral palsy, tone, gait, orthoses, kinesio taping,
vestibular rehabilitation); psychology (development, clinical, trauma, psychometrics and WISC,
projective tests, neuropsychology, ACT, schema therapy, solution-focused, family systems,
Gottman, psychodynamic terms); special education (2018 regulation, BEP, evidence-based
practices, single-subject research, reading and maths instruction, early intervention,
ETEÇOM / İVO-ODS); diagnoses (DSM-5); assessment tools. A third round added the basics that
specialist lists miss: abbreviations and professions (OT → ergoterapist, PT → fizyoterapist,
SLP → dil ve konuşma terapisti, with plurals and "OT services"-type combinations), research
methods and academic language (literatür taraması, sistematik derleme, randomize kontrollü
çalışma, örneklem, etki büyüklüğü, hakemli dergi), clinical/medical/neuroscience basics (ayırıcı
tanı, eş tanı, yaygınlık, nöroplastisite) and the everyday language of therapists, parents and
teachers (uyarı işaretleri, vaka yükü, tuvalet eğitimi). On 63 basic sentences, the number with a
wrong key term dropped from about 20 to 3–4, with no regressions on the earlier 90 test sentences
or the real recordings. Left on purpose: bare "sample" and "limitations" are not forced (they also
mean *örnek* and ICF *kısıtlılık*); only "sample size", "limitations of the study" etc. are.

## Sources, in order of priority

1. **DİLGEM's own materials** (training slides, trainer notes, website texts, social media
   posts, course lists 2019–2025, and transcripts of real training recordings). Where DİLGEM
   uses a term consistently, that wins over the general literature.
2. **Turkish professional literature**: the DSM-5 Turkish edition (Köroğlu), DergiPark articles
   (Hacettepe, Anadolu, Ankara and Gazi special education and speech-language therapy
   departments), YÖK theses, the MEB *Özel Eğitim Hizmetleri Yönetmeliği* (2018), and Turkish
   adaptation studies of the tests.
3. **Practitioner sources** (clinic and association sites) only where no academic Turkish
   source exists, which is mostly the case for play-therapy skill names and the CBT
   distortions. Rows based on these are marked in the notes column of `glossary_sources.tsv`.

## DİLGEM's subjects (what the glossary covers)

Ranked by how often DİLGEM teaches them: play therapy (ÇMOT, filial terapi / CPRT),
developmental tests (AGTE, Frostig, Gesell, Metropolitan, Peabody), DIR Floortime,
DEHB and attention assessment (d2, Burdon, Stroop, MOXO, ATHİS), stuttering (Lidcombe, Palin PCI,
RESTART-DCM, hızlı ve bozuk konuşma), sensory integration (SIPT, Duyu Profili), autism models
(JASPER, ESDM, SCERTS), feeding and swallowing, WISC-R, psychotherapy (BDT, ACT), special
education (BEP, RAM).

## Important choices

| Term | Chosen | Why |
|------|--------|-----|
| trainee(s) | **katılımcı(lar)** | DİLGEM's public texts say *katılımcı*; *kursiyer* is not used (it is still translated back to "trainee"). The translator alone gives *stajyer* or even *trenler*. |
| authoritative parenting | **demokratik ebeveynlik** | The translator gives *otoriter* (= authoritarian), the opposite style. |
| engagement / regulation (JASPER) | **katılım / düzenleme** | Turkish JASPER chapter (Özen, Önal, Tıkıroğlu 2024) and DİLGEM's JASPER article. The translator gives *nişan* and *yönetmelik*. |
| severity rating, verbal contingencies (Lidcombe) | **şiddet puanlama, sözel geribildirim** | DİLGEM's Lidcombe certificate page. Two older DİLGEM articles have machine-translation errors (*sözlü olasılıklar*). |
| circles of communication (DIR) | **iletişim çemberleri** | Kars (2020), DergiPark. |
| autism spectrum disorder, ADHD | **otizm spektrum bozukluğu, DEHB** | Common clinical usage. The official DSM-5 Turkish forms (*otizm açılımı kapsamında bozukluk*, *dikkat eksikliği/aşırı hareketlilik bozukluğu*) are rarely used by practitioners; they are listed as alternatives. |
| conduct disorder | **davranım bozukluğu** | *Davranış bozukluğu* just means "behaviour problem". |
| executive functions | **yürütücü işlevler** | Child psychiatry usage (*yönetici işlevler* is also translated back). |
| school readiness | **okula hazırbulunuşluk** | Academic and MEB usage (*okul olgunluğu* is also translated back). |
| time-out | **ortamdan uzaklaştırma** | Turkish ABA literature (the translator gives *zaman aşımı*). |
| occupational therapy | **ergoterapi** | The translator gives *iş terapisi* or *mesleki terapi*. |
| filial therapy | **filial terapi** | The translator gives *evlat terapisi* or *çocuk terapisi*; Turkish → English gave "affiliate therapy" or "branch approach". |
| BEP | **IEP** (en) | Officially *Bireyselleştirilmiş Eğitim Programı* (not "plan"). |
| occupational performance, COPM | **aktivite performansı, KAPÖ** | Hacettepe ergoterapi usage. The translator gives *iş performansı*. "occupation" alone is not forced (it also means job). |
| range of motion | **eklem hareket açıklığı (EHA)** | Turkish physiotherapy literature; the translator gives *hareket aralığı*. |
| trunk control, crawling | **gövde kontrolü, emekleme** | The translator gives *bagaj* and *sürünme*. Bare "trunk" is not forced (car boot). |
| kinesio taping | **kinezyo bantlama** | Bayrakcı Tunay & Baltacı (2017). |
| fronting, stopping, cluster reduction | **önleştirme, duraklaştırma, ünsüz öbeği daralması** | Topbaş's Turkish phonological-process terms. |
| minimal pairs | **minimal çiftler** | The translator gives *minimum çiftler* / "minimal couples". |
| IDDSI levels | **İnce, Çok Hafif Kıvamlı, Hafif Kıvamlı …** | The official Turkish IDDSI document. |
| cognitive defusion, self-as-context | **bilişsel ayrışma, bağlamsal benlik** | Turkish ACT literature; the translator gives *bilişsel çözünürlük*. |
| zone of proximal development, scaffolding | **yakınsal gelişim alanı, iskele kurma** | The translator gives *proximal gelişim bölgesi* and *iskele*. |
| transference | **aktarım** (en>tr) | The translator gives *transfer*; Turkish → English *aktarım* also means "transmission". |
| baseline, multiple probe design, fidelity | **başlama düzeyi, çoklu yoklama modeli, uygulama güvenirliği** | Turkish single-subject research (Tekin-İftar). The translator gives *temel çizgi*, *çoklu sonda*, *sadakat*. |
| least restrictive environment | **en az sınırlandırılmış eğitim ortamı** | Wording of the 2018 regulation. |
| gifted | **özel yetenekli** | MEB usage (BİLSEM). |

## Terms where Turkish usage is split

The first form is used; the others are in `glossary_sources.tsv`:
tracking (*izleme* / takip etme / betimleme), mindfulness (*bilinçli farkındalık* / bilgece farkındalık),
co-regulation (*eş düzenleme* / birlikte düzenleme; no Turkish source defines it yet),
attunement (*uyumlanma* / duygusal uyum), sibling rivalry (*kardeş kıskançlığı* / kardeş rekabeti),
developmental delay (*gelişimsel gerilik* / gelişimsel gecikme), AAC (*alternatif ve destekleyici iletişim* /
artırıcı ve alternatif iletişim), case study (*vaka çalışması* / olgu sunumu).

Also split: engelli birey (regulation) / … yetersizliği olan birey (MEB programmes, academia);
okul olgunluğu / okula hazırbulunuşluk; aktivite / okupasyon / uğraşı (OT); -pleji / -parezi
(used interchangeably in Turkish physiotherapy); yürütücü / yönetici işlevler.

**Not forced on purpose:** everyday words with other meanings: *play, prompt, session, praise,
limit, tracking, labeling, occupation, trunk, tone, conservation, craving, placement, block,
stopping, probe, aspiration* (English) and *dikkat, katılım, düzenleme, ipucu, aktivite, uzatma,
kaçınma, dengeleme, yüceltme* (Turkish), except inside longer terms (*muscle tone*, *trunk
control*, *silent aspiration*). Single words without a confirmed source are not forced either.
Also the ambiguous abbreviations **ACT** (Landreth's limit-setting model, or Acceptance and
Commitment Therapy) and **CAS** (Childhood Apraxia of Speech, or a test). All-capital names longer
than 4 letters (CALMS, JASPER) match in capitals or with a capital first letter only, so the
English words *calms* and *prompt* are left alone.

## Corrections of misheard words

From DİLGEM's own 154-minute *Oyun Terapisi* transcript: speech recognition wrote *Çocuk
Merkezi Oyun Terapisi* 17 times (correct: *Merkezli*, 6 times), and *Filaterapi*, *Filihal*, *Gurney*
(Guerney). These are fixed in the `[tr>tr]` section before translation.

## How the program uses the glossary

- Names and abbreviations are kept exactly as written; short ones (up to 4 capitals) only match
  in capitals, so *cars*, *aba* or *dir* are left alone.
- Forced terms are put into the sentence before translating. Turkish terms also match with
  endings (*filial terapide*). Suffixes the translator glues to a forced Turkish word are
  repaired (vowel harmony, buffer letters, consonant softening: *pekiştireci*, *öz düzenlemeyi*,
  *iletişim çemberlerini*, *hedef davranıştan*).
- Sentences changed by the glossary are also translated unchanged, and the version that contains
  more glossary terms is kept (a tie keeps the unchanged one). This prevents the forced words
  from confusing Turkish → English sentences.

## Test results

Measured with the offline translator (NLLB) on 25 English and 15 Turkish trainer sentences and
on real recordings (10 minutes of the *Oyun Terapisi – 3. Gün* training, 5 minutes of an English
CBT video):

- Domain sentences: the technical terms were wrong in most of them with the old glossary and
  right in 39 of 40 with the new one (the remaining one: *eş düzenleme* → "co-editing").
- Real training recording: 10 of 136 subtitles changed, all improvements or neutral
  ("branch approach" → "filial approach", "speech-language pathologists" → "therapists",
  "physical therapists" → "physiotherapists").
- Speech recognition was unchanged by the new hints (99.9 % identical text).
- Translation takes about 1.7× longer for sentences that contain glossary terms (a 2-hour
  recording: about 1–2 extra minutes).
- Second round (occupational therapy, physiotherapy, psychology, special education, speech and
  language therapy), 30 English and 20 Turkish sentences: most technical terms were wrong
  without these entries and right with them (e.g. *KAPÖ, aktivite performansı* instead of
  *iş performansı*, *eklem hareket açıklığı*, *bilişsel ayrışma*, *yakınsal gelişim alanı*,
  *çoklu yoklama modeli … başlama düzeyi*; Turkish → English "transference", "zone of proximal
  development", "multiple probe design", "range of motion"). The earlier 40 sentences and the
  real recordings did not get worse. Still wrong: *Bloklar ve uzatmalar* → "stretch marks"
  (*uzatma* is not forced because it is an everyday word) and "aspiration" can be dropped.

## Keeping it up to date

- Add terms the translator gets wrong to section 4 of your `glossary.txt` (Edit glossary… button).
- Add recurring speech-recognition mistakes to `[tr>tr]`.
- Your `glossary.txt` can hold private names (trainers, speakers); it is never uploaded.
- The verified Landreth Turkish edition (*Oyun Terapisi: İlişki Sanatı*) was not available
  online; its toy-category names and "esteem-building responses" should be checked against the
  book (marked in `glossary_sources.tsv`).
