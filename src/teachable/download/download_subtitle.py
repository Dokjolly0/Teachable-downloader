from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any, Dict, Mapping, Optional
from urllib.parse import urljoin

if TYPE_CHECKING:
    from src.teachable.teachable_downloader import TeachableDownloader

import requests
import yt_dlp

import src.helpers.logger as logger
from src.helpers.ffmpeg import check_ffmpeg_available, install_ffmpeg


def _subtitle_filename(
    output_path: str, title: str, video_index: int, lang: str, ext: str
) -> str:
    """Return the subtitle filename path for a given language and extension."""
    subtitle_filename = "{:02d}-{}.{}.{}".format(video_index, title, lang, ext)
    return os.path.join(output_path, subtitle_filename)


def download_subtitle(
    self: "TeachableDownloader", link, title, video_index, output_path
) -> "TeachableDownloader":
    """Download subtitles for a given video. This version:
    - Checks if subtitle files already exist and skips them.
    - Uses yt-dlp to probe subtitle URLs and downloads the subtitle files if not present.
    """
    # Check if ffmpeg is available
    ffmpeg_path = check_ffmpeg_available()
    if not ffmpeg_path:
        install_ffmpeg()

    ydl_opts: yt_dlp._Params = {
        "format": "best",
        "merge_output_format": "mp4",
        "postprocessors": [
            {"key": "FFmpegVideoConvertor", "preferedformat": "mp4"},
            {"key": "FFmpegMetadata"},
        ],
        "ignoreerrors": True,
        "http_headers": self.headers,
        "allsubtitles": True,
        "subtitleslangs": ["all"],
        "concurrent_fragment_downloads": 10,
        "writesubtitles": True,
        # Set outtmpl to path prefix so we can name files manually
        "outtmpl": os.path.join(str(output_path), str(title)),
        "verbose": True if self.verbose > 0 else False,
    }

    if ffmpeg_path != "ffmpeg":
        ydl_opts["ffmpeg_location"] = ffmpeg_path

    info_json: Optional[Mapping[str, Any]] = None
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(link, download=False)
                info_json = ydl.sanitize_info(info) if info else None
            except Exception as e:
                logger.log(
                    f"Could not probe subtitles metadata for: {title} cause: {e}",
                    status=logger.Status.WARNING,
                )
                info_json = None
    except Exception as e:
        logger.log(
            f"yt-dlp probe failed for subtitles: {e}", status=logger.Status.WARNING
        )
        info_json = None

    subtitle_links: Dict[str, Dict[str, str]] = {}
    if info_json and isinstance(info_json, dict) and "requested_subtitles" in info_json:
        requested = cast(Dict[str, Any], info_json["requested_subtitles"])
        for lang, sub_info in requested.items():
            # sub_info is expected to have url and ext
            subtitle_links[lang] = {
                "url": sub_info.get("url"),
                "ext": sub_info.get("ext"),
            }

    # If no requested_subtitles, try to inspect 'subtitles' or 'automatic_captions'
    if not subtitle_links and info_json:
        subs = info_json.get("subtitles") or info_json.get("automatic_captions") or {}
        for lang, entries in subs.items():
            # entries is a list of dicts with 'url' and 'ext'
            if isinstance(entries, list) and entries:
                first = entries[0]
                subtitle_links[lang] = {
                    "url": first.get("url"),
                    "ext": first.get("ext"),
                }

    req = None
    for lang, sub in subtitle_links.items():
        subtitle_path = _subtitle_filename(
            output_path, title, video_index, lang, sub["ext"]
        )
        # Skip if already downloaded
        if os.path.isfile(subtitle_path) and os.path.getsize(subtitle_path) > 0:
            logger.log(
                "Skipping existing subtitle: " + os.path.basename(subtitle_path),
                status=logger.Status.INFO,
            )
            continue

        base_url = sub.get("url")
        if not base_url:
            logger.log(
                f"No subtitle URL for {title} lang={lang}", status=logger.Status.DEBUG
            )
            continue

        try:
            # First request to get relative path (some subtitle endpoints return manifest)
            req = requests.get(base_url, headers=self.headers, timeout=30)
            req.raise_for_status()
        except Exception as e:
            logger.log(
                f"Could not fetch subtitle base URL for {title} lang={lang}: {e}",
                status=logger.Status.WARNING,
            )
            continue

        # If response looks like a VTT manifest or another index, attempt to extract the candidate path
        try:
            # Heuristic: sometimes the actual file is referenced inside the response text
            relative_path = ""
            text = req.text or ""
            # Try to find a plausible subtitle line (very defensive)
            lines = text.splitlines()
            if len(lines) >= 6:
                relative_path = lines[5].strip()
            # Fallback to direct URL if we could not find a relative path
            full_url = urljoin(base_url, relative_path) if relative_path else base_url

            response = requests.get(full_url, headers=self.headers, timeout=30)
            response.raise_for_status()
            # Write file bytes (binary)
            with open(subtitle_path, "wb") as f:
                f.write(response.content)
            logger.log(
                "Downloaded subtitle: " + os.path.basename(subtitle_path),
                status=logger.Status.INFO,
            )
        except Exception as e:
            logger.log(
                f"Could not download subtitle: {title} lang={lang} cause: {e}",
                status=logger.Status.WARNING,
            )
    return self
