from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, Mapping, Optional, cast

if TYPE_CHECKING:
    from src.teachable.teachable_downloader import TeachableDownloader

import os
from urllib.parse import urljoin

import requests
import yt_dlp

import src.helpers.logger as logger
from src.helpers.ffmpeg import check_ffmpeg_available, install_ffmpeg


# This function is needed because yt-dlp subtitle downloader is not working
def download_subtitle(
    self: "TeachableDownloader", link, title, video_index, output_path
) -> TeachableDownloader:
    # Check if ffmpeg is available
    ffmpeg_path = check_ffmpeg_available()
    if not ffmpeg_path:
        install_ffmpeg()

    ydl_opts: yt_dlp._Params = {
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "merge_output_format": "mp4",
        "postprocessors": [
            {
                "key": "FFmpegVideoConvertor",
                "preferedformat": "mp4",
            },
            {
                "key": "FFmpegMetadata",
            },
        ],
        "ignoreerrors": True,
        "http_headers": self.headers,
        "allsubtitles": True,
        "subtitleslangs": ["all"],
        "concurrent_fragment_downloads": 10,
        "writesubtitles": True,
        "outtmpl": os.path.join(str(output_path), str(title)),
        "verbose": True if self.verbose > 0 else False,
    }

    # Se ffmpeg è in una path specifica, aggiungila alle opzioni
    if ffmpeg_path != "ffmpeg":
        ydl_opts["ffmpeg_location"] = ffmpeg_path

    info_json: Optional[Mapping[str, Any]] = None
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(link, download=False)
            info_json = ydl.sanitize_info(info)
    except Exception as e:
        logger.log(f"Could not download subtitle: {title} cause: {e}")

    subtitle_links = {}
    if info_json and isinstance(info_json, dict) and "requested_subtitles" in info_json:
        requested = cast(Dict[str, Any], info_json["requested_subtitles"])
        for lang, sub_info in requested.items():
            subtitle_links[lang] = {"url": sub_info["url"], "ext": sub_info["ext"]}

    # Print the subtitle links and language names
    req = None
    for lang, sub in subtitle_links.items():
        subtitle_filename = "{:02d}-{}.{}.{}".format(
            video_index, title, lang, sub["ext"]
        )
        file_path = os.path.join(output_path, subtitle_filename)
        if os.path.isfile(file_path):
            logger.log(
                "Skipping existing subtitle: " + subtitle_filename,
                status=logger.Status.INFO,
            )
        else:
            base_url = sub["url"]
            try:
                req = requests.get(sub["url"], headers=self.headers)
            except Exception as e:
                logger.log(
                    f"Could not download subtitle: {title} cause: {e}",
                    status=logger.Status.WARNING,
                )
            relative_path = (
                req.text.split("\n")[5] if isinstance(req, requests.Response) else ""
            )
            full_url = urljoin(base_url, relative_path)
            try:
                response = requests.get(full_url, headers=self.headers)
                with open(file_path, "wb") as f:
                    f.write(response.content)
            except Exception as e:
                logger.log(
                    f"Could not download subtitle: {title} cause: {e}",
                    status=logger.Status.WARNING,
                )
            logger.log(
                "Downloaded subtitle: " + subtitle_filename,
                status=logger.Status.INFO,
            )
    return self
