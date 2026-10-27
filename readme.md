<div align="center">

<img src="https://raw.githubusercontent.com/kareem2099/DotScramble/main/assets/icons/png/dotscramble-128.png" width="104" alt="DotScramble icon: a dot dissolving into pixels">

# DotScramble: blur faces, license plates and text in photos on Linux

**Hide what shouldn't be seen, before you share.** A free, open-source photo privacy studio:
blur, pixelate or black-bar **faces, eyes, license plates and text**, strip or fake **EXIF and
GPS metadata**, and hide faces from **AI face detection**. Everything runs on your computer.

[![Version](https://img.shields.io/badge/version-1.5.3-00BCD4?style=flat-square)](https://github.com/kareem2099/DotScramble/blob/main/CHANGELOG.md)
[![License: Apache 2.0](https://img.shields.io/badge/license-Apache%202.0-2FD38B?style=flat-square)](https://github.com/kareem2099/DotScramble/blob/main/LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-2FC8F0?style=flat-square&logo=python&logoColor=white)](https://github.com/kareem2099/DotScramble/blob/main/requirements.txt)
[![Linux](https://img.shields.io/badge/platform-Linux%20x86__64-FFB547?style=flat-square&logo=linux&logoColor=black)](#supported-systems)
[![CI](https://img.shields.io/github/actions/workflow/status/kareem2099/DotScramble/ci.yml?branch=main&label=tests&style=flat-square)](https://github.com/kareem2099/DotScramble/actions/workflows/ci.yml)
[![7 languages](https://img.shields.io/badge/languages-7-7C5CFF?style=flat-square)](#languages-and-themes)
[![Part of DotSuite](https://img.shields.io/badge/part%20of-DotSuite-FF6B9A?style=flat-square)](https://dotsuite.dev/en)

[**Download**](https://github.com/kareem2099/DotScramble/releases/latest) ·
[**Website**](https://dotsuite.dev/en/product/dotscramble) ·
[**Changelog**](https://github.com/kareem2099/DotScramble/blob/main/CHANGELOG.md) ·
[**DotSuite**](https://dotsuite.dev/en) ·
[**All my tools**](https://universe.dotsuite.dev)

</div>

![DotScramble finding four faces in a group photo and pixelating them](https://raw.githubusercontent.com/kareem2099/DotScramble/main/docs/screenshots/hero.png)

---

## Why DotScramble?

A photo you are about to post often shows more than you meant to: the faces of people who never
agreed to be online, a car's number plate, a name on a badge, an address on a parcel, and the
exact GPS location hidden in the file. DotScramble removes all of that in one place:

1. **Open** a photo, or drop it on the window.
2. **Pick what to hide** (faces, eyes, plates, text, a word, or regions you draw) and **how**
   (blur, pixelate, black bar, mosaic…).
3. **Apply, compare and save.** Choose whether the saved file keeps, strips or fakes its metadata.

- **Private:** your photos are processed on your machine and never uploaded.
- **See before you commit:** *Detect* shows every region it will hide, and you click one to
  skip it. *Compare* puts the original and the result side by side.
- **Honest:** it tells you how many regions it hid, and it refuses to pretend: if detection
  can't run, you get an error, never a "done" with the face still visible.
- **AI-aware:** blurring is enough for people, not always for software. AI Evasion targets
  face *detectors* too.
- **Free and open source:** Apache 2.0, part of the [DotSuite](https://dotsuite.dev/en) family.
  An optional Pro plan adds AI-powered detection and the advanced tools.

## Features

| | |
|---|---|
| 🎯 **What to hide** | Face, eyes, full body, license plate, any text (OCR), one specific word, regions you draw, or the whole image. |
| 🎨 **How to hide it** | Blur, pixelation, black bar, gradient, mosaic, frosted glass and oil paint, with strength, block size and opacity controls. |
| 🛡️ **AI Evasion** | *Hybrid* blurs the face for people and hides it from AI face detection; *Invisible* leaves it looking unchanged while hiding it from the detector. |
| 🔍 **Detect preview** | Every region outlined before anything changes. Click a region to skip it; with several faces you protect exactly the ones you choose. |
| ↔️ **Compare** | A before / after split view with a draggable divider. |
| 🔎 **Zoom and pan** | Mouse-wheel zoom around the cursor, fit or 100 %, and drag to move around a large photo. |
| ⚡ **Live preview** | Change a setting and the result updates on its own, without stacking the effect. |
| 🧾 **Metadata on save** | Keep it, strip GPS, camera and device tags, or replace them with believable decoys (Ghost, Troll, Artist), or set every field yourself. A report shows exactly what will happen before the file is written. |
| 📦 **Batch processing** | One detection mode and effect for a whole folder, with progress, a summary, and per-file errors. |
| 💾 **Presets, undo and redo** | Save your favourite settings; step back and forward through every change. |
| 🌍 **7 languages** | English, العربية, فارسی, Español, Русский, Deutsch, Türkçe, with right-to-left layouts and correct plurals. |
| 🎨 **16 themes** | Midnight, Light, Nord, Dracula, Tokyo Night, Catppuccin, Rosé Pine, Gruvbox and more; every screen follows the theme. |
| 🔐 **Signed updates** | Releases are built by GitHub Actions and signed; the app checks the checksum *and* the GPG signature before it installs anything. |

### Free and Pro

Everything you need to hide faces, plates and metadata is free. Pro (the **DotScramble Max**
plan on [DotSuite](https://dotsuite.dev/en/product/dotscramble)) adds AI-powered tools:

| | Free | Pro |
|---|:---:|:---:|
| All 7 effects, Detect preview, Compare, zoom, live preview | ✅ | ✅ |
| Face and eye detection | Haar cascades | **AI face ovals** and tilted eye bars (MediaPipe) |
| Manual regions and full image | ✅ | ✅ |
| Full body, license plates, text (OCR), one specific word | | ✅ |
| AI Evasion (Hybrid and Invisible) | | ✅ |
| Strip or fake metadata, per-field metadata editor | | ✅ |
| Batch processing | 3 images per batch | Unlimited |

Activate Pro from **Help → Upgrade to Pro**: you sign in on dotsuite.dev in your browser and
the app is activated automatically.

## AI Evasion

A blurred face is unreadable to people, yet face *detectors* can often still find it, and a
photo that software can find a face in can be indexed, matched and tracked. AI Evasion adds a
small, optimized pattern of noise to the face region until a face detector no longer finds a
face there.

```
Original → face oval found → black-box optimisation (SPSA) against the detector → protected face
```

- **Hybrid:** blur for people plus the adversarial pattern for software.
- **Invisible:** the face looks the same to people; only the detector is fooled.
- It runs on the CPU and takes about **30–90 seconds per face**, with a progress dialog you can
  cancel.
- The result is reported honestly: **complete**, **partial** (with the evasion rate), or
  **failed** (the face is still blurred, but evasion was not verified).
- Save the result as **PNG**: JPEG compression can weaken the pattern.

The pattern is tuned against the face detector DotScramble itself uses (MediaPipe). It is not a
guarantee against every face recognition system, so treat it as an extra layer on top of a
visible effect, not a replacement for one.

## Install

Every package installs the same app. All of them are on the
[Releases page](https://github.com/kareem2099/DotScramble/releases/latest).

| Method | How | Best for |
|--------|-----|----------|
| **AppImage** | `chmod +x DotScramble-Linux-x86_64.AppImage && ./DotScramble-Linux-x86_64.AppImage` | any distribution, no install |
| **Debian / Ubuntu / Kali / Mint** | `sudo apt install ./DotScramble-Linux-x86_64.deb`, then run `dotscramble` | app-menu integration |
| **Arch / Manjaro** | `sudo pacman -U DotScramble-Linux-x86_64.pkg.tar.zst`, then run `dotscramble` | Arch-based systems |
| **Portable** | `tar xzf DotScramble-Linux-x86_64.tar.gz && ./DotScramble` | one binary, anywhere |
| **From source** | [see below](#from-source) | development |

Optional, for the text and word modes:

```bash
sudo apt install tesseract-ocr        # Fedora: sudo dnf install tesseract · Arch: sudo pacman -S tesseract
```

- **AppImage:** if it won't start because of FUSE, install `libfuse2` (`libfuse2t64` on
  Ubuntu 24.04+) or run it with `--appimage-extract-and-run`.
- **AI model:** the first time you use a Pro AI feature, DotScramble asks to download Google's
  MediaPipe face landmark model (about 8 MB).

## Supported systems

The packages are built on Ubuntu 22.04 and need **glibc 2.35 or newer** on **x86_64**:

| Distribution | Works |
|--------------|:-----:|
| Ubuntu 22.04 LTS and newer (Linux Mint 21+, Pop!\_OS, Zorin, elementary OS 7+) | ✅ |
| Debian 12 (bookworm) and newer | ✅ |
| Kali Linux (rolling) | ✅ |
| Fedora 36 and newer | ✅ |
| Arch, Manjaro, EndeavourOS | ✅ |
| openSUSE Tumbleweed | ✅ |
| Ubuntu 20.04, Debian 11, RHEL / Rocky / Alma 9 and older | ❌ glibc too old: [run from source](#from-source) |
| Windows, macOS | not yet |

Works on X11 and Wayland (GNOME, KDE and others), and snaps to half the screen like any window.

### Verify your download

Every release has a `SHA256SUMS` file, a detached GPG signature (`.asc`) for every package, and
the public key (`DotScramble-signing-key.asc`):

```bash
sha256sum -c SHA256SUMS --ignore-missing          # checks the files you downloaded
gpg --import DotScramble-signing-key.asc
gpg --verify DotScramble-Linux-x86_64.AppImage.asc DotScramble-Linux-x86_64.AppImage
```

Releases are signed by **FreeRave &lt;kareem209907@gmail.com&gt;**, with this key fingerprint:

```
0F04 6781 3146 DE68 272E  DC82 145D 3459 56DE 18D2
```

Check it after importing with `gpg --fingerprint 145D345956DE18D2`. A `Good signature` from that
key means the file is exactly what the release workflow built. The built-in updater checks the
same signature against the same pinned fingerprint before it installs an update.

### From source

```bash
git clone https://github.com/kareem2099/DotScramble && cd DotScramble
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python src/main.py
```

Python 3.10 or newer. `requirements.txt` pins OpenCV to the 4.x contrib build on purpose:
OpenCV 5 no longer ships the Haar cascade files the free face, eye and body detection uses.

## Usage

![Before / after split view: drag the divider to compare the original with the blurred face](https://raw.githubusercontent.com/kareem2099/DotScramble/main/docs/screenshots/compare.png)

**The basic flow:** open a photo (`Ctrl+O`, the image browser, or drag and drop) → pick what to
hide in step 1 → pick the effect in step 2 → fine-tune in step 3 → **Apply effect**
(`Ctrl+Enter`) → **Save** (`Ctrl+S`).

- **Detect** (`Ctrl+F`): outlines what the current mode finds. Click a region to skip it;
  **Apply** then hides only the regions still outlined.
- **Manual:** choose *Manual* and drag on the photo to draw as many regions as you need.
- **Targeted text:** type a word (a name, a phone number) and only that word is hidden.
- **Compare** (`Ctrl+Shift+C`): drag the divider to see the original and the result.
- **Live preview:** turn it on in the toolbar and every change re-applies by itself.
- **Metadata on save:** in step 4 choose *Keep*, *Strip* or *Decoy*. When you save, a summary
  shows exactly which fields will be kept, removed or replaced.
- **Batch** (`Ctrl+B`): add files or a whole folder, pick a mode and an effect, choose an output
  folder, and start.
- **Presets:** *Presets → Save Current Settings*, then load them any time.

### Keyboard shortcuts

| Shortcut | Action | Shortcut | Action |
|----------|--------|----------|--------|
| `Ctrl+O` | Open an image | `Ctrl+S` | Save the result |
| `Ctrl+Enter` | Apply the effect | `Ctrl+D` | Clear selections |
| `Ctrl+Z` | Undo | `Ctrl+Y` | Redo |
| `Ctrl+F` | Detect preview | `Ctrl+Shift+C` | Compare |
| `Ctrl++` / `Ctrl+-` | Zoom in / out | `Ctrl+0` / `Ctrl+1` | Fit / actual size |
| `Ctrl+B` | Batch processing | | |

### Languages and themes

![DotScramble in Arabic, right to left, on the light theme](https://raw.githubusercontent.com/kareem2099/DotScramble/main/docs/screenshots/arabic.png)

**View → Language** switches between English, العربية, فارسی, Español, Русский, Deutsch and
Türkçe on the fly; Arabic and Persian use a right-to-left layout. DotScramble starts in your
system language when it is one of them. **View → Themes** has 16 themes, and every dialog follows
the one you pick.

### Updates

DotScramble checks GitHub for a new release in the background. When there is one, it downloads
the file that matches how you installed it, verifies the checksum and the signature, and offers
to restart. If a version is ever retired, an older copy shows a clear **Update required** screen
with a download button. Running from source never updates itself. The AppImage also carries
update information, so AppImageUpdate, Gear Lever and AppImageLauncher can update it too.

## What goes online

Your photos never leave your computer. DotScramble connects only to:

| When | Where | Why |
|------|-------|-----|
| Startup and *Check for Updates* | `api.github.com`, `raw.githubusercontent.com` | new releases and the supported-version policy |
| Downloading an update | `github.com` release files | the new version |
| Activating or re-checking Pro | `dotsuite.dev`, `core.dotsuite.dev` | your licence |
| First use of a Pro AI feature, if you agree | `storage.googleapis.com` | the MediaPipe face model (about 8 MB) |

Settings, presets and history stay in `~/.local/share/DotScramble`.

## FAQ

<details>
<summary><b>How do I blur faces in a photo on Linux?</b></summary>

Open the photo, keep **Face** selected in step 1, pick **Blur** (or Pixelation, Black Bar,
Mosaic…) in step 2, and press **Apply effect**. Press **Detect** first if you want to see the
faces it found and skip some of them.
</details>

<details>
<summary><b>How do I hide a license plate or a number plate?</b></summary>

Choose **License Plate** in step 1 (Pro), or **Manual** and draw a rectangle over the plate
(free). Pixelation or Black Bar work best for plates.
</details>

<details>
<summary><b>How do I remove EXIF and GPS location from a photo?</b></summary>

In step 4, **Metadata on save**, choose **Strip** to remove GPS, camera and device tags, or
**Decoy** to replace them with believable fake values. When you save, a report lists every field
before the file is written. (Metadata tools are part of Pro.)
</details>

<details>
<summary><b>Can DotScramble hide my face from AI face recognition?</b></summary>

Its AI Evasion mode (Pro) adds an optimized noise pattern until a face detector no longer finds
the face, and reports whether that fully worked. It is tuned against the MediaPipe detector the
app uses and is not a guarantee against every system, so use it together with a visible effect
(the *Hybrid* mode does both).
</details>

<details>
<summary><b>Can I blur one specific word, like a name, in a screenshot?</b></summary>

Yes: choose **Targeted Text** (Pro) and type the word. It needs Tesseract OCR
(`sudo apt install tesseract-ocr`). **Text** hides every piece of text it finds instead.
</details>

<details>
<summary><b>Can I blur faces in many photos at once?</b></summary>

Yes, with **Batch processing** (`Ctrl+B`): add a folder, pick the mode and the effect, and
DotScramble processes every image and reports any that failed. Free batches hold three images.
</details>

<details>
<summary><b>Does DotScramble upload my photos?</b></summary>

No. All detection and effects run locally. See [What goes online](#what-goes-online) for the few
connections it does make, none of which send your images.
</details>

<details>
<summary><b>Is DotScramble free?</b></summary>

Yes. It is open source under Apache 2.0, and blurring faces, plates you draw and whole images is
free forever. Pro adds the AI-powered detection, AI Evasion, the metadata tools and unlimited
batches.
</details>

<details>
<summary><b>Does it support Arabic and other languages?</b></summary>

Yes: English, العربية, فارسی, Español, Русский, Deutsch and Türkçe, with a right-to-left layout
for Arabic and Persian and correct plural forms in every language. Translations other than
English and Arabic are new: corrections are very welcome.
</details>

<details>
<summary><b>Which Linux distributions does it run on? What about Windows and macOS?</b></summary>

Any x86_64 distribution with glibc 2.35 or newer: Ubuntu 22.04+, Debian 12+, Fedora 36+, Kali,
Arch and others (see [Supported systems](#supported-systems)). On older systems, run it from
source. Windows and macOS builds are planned once they can be tested properly.
</details>

## Part of DotSuite

DotScramble is one of the developer and desktop tools in **[DotSuite](https://dotsuite.dev/en)**
by FreeRave:

- [**DotMorph**](https://dotsuite.dev/en/product/dotmorph): the radial-menu file converter for
  Linux.
- [**DotGhostBoard**](https://dotsuite.dev/en/product/dotghostboard): encrypted clipboard
  manager for Linux.
- [**DotShare**](https://dotsuite.dev/en/product/dotshare): share your code journey from
  VS Code.
- …and everything else at [universe.dotsuite.dev](https://universe.dotsuite.dev).

## Develop

```bash
pip install -r requirements.txt pytest
QT_QPA_PLATFORM=offscreen pytest -q tests
```

- **Tests** run offscreen and on every push in CI. The licence module (`src/managers/license_manager.py`)
  is not in the repository: tests that need it run in CI, where it comes from a secret.
- **Translations** live in `src/assets/locales/<lang>.json`; counted strings use CLDR plural
  forms (`{"one": …, "other": …}`). Adding a language is one JSON file plus an entry in
  `languages.json`.
- **Styling** lives in one stylesheet, `assets/themes/theme_template.qss`, filled from the 16
  themes in `assets/themes/themes.json`. Widgets only set object names and `variant` / `role`
  properties.

```
src/
  main.py               entry point
  config.py             settings, version, update source
  views/                main window, canvas (zoom / compare / detect overlay), sidebar widgets, icons
  models/               detection engine (Haar, MediaPipe, OCR), effects, AI evasion (SPSA)
  managers/             themes, localization (plurals, RTL), licence, local auth, database
  assets/locales/       en, ar, fa, es, ru, de, tr
core/                   image picker, batch processor, auto-updater, version gate, metadata spoofer
gui/                    batch window, metadata editor and save report
assets/                 themes (QSS + JSON), icons
tests/
.github/workflows/      ci.yml (tests), release.yml (build, smoke-test, sign, publish)
version_policy.json     the oldest version still supported
```

Issues and pull requests are welcome on [GitHub](https://github.com/kareem2099/DotScramble/issues).
Start with [CONTRIBUTING.md](https://github.com/kareem2099/DotScramble/blob/main/CONTRIBUTING.md).

If DotScramble keeps your photos private, you can support it through
[GitHub Sponsors](https://github.com/sponsors/kareem2099), [Ko-fi](https://ko-fi.com/freerave)
or [Buy Me a Coffee](https://buymeacoffee.com/freerave).

## License

[Apache 2.0](https://github.com/kareem2099/DotScramble/blob/main/LICENSE) © FreeRave (Kareem).
PySide6 (Qt for Python) is used under the LGPL v3. Part of [DotSuite](https://dotsuite.dev/en).
