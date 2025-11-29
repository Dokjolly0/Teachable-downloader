from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.teachable.teachable_downloader import TeachableDownloader

import yt_dlp

import src.helpers.logger as logger
from src.helpers.ffmpeg import check_ffmpeg_available, install_ffmpeg


def _target_video_path(output_path: str, title, video_index) -> str:
    """Return expected final mp4 path for a given lecture to support resume checks."""
    return os.path.join(
        output_path, "{:02d}-{}.mp4".format(int(video_index), str(title))
    )


def download_video(
    self: "TeachableDownloader", link, title, video_index, output_path
) -> "TeachableDownloader":
    """Download video using yt_dlp with resume-aware checks.

    Behavior changes:
    - If final mp4 exists and has size > 0, skip the download.
    - Uses yt-dlp's default resume capabilities for partial downloads.
    - Logs more informative warnings if download fails.
    """
    # Check if ffmpeg is available
    ffmpeg_path = check_ffmpeg_available()
    if not ffmpeg_path:
        install_ffmpeg()

    final_path = _target_video_path(output_path, title, video_index)
    # Skip if file exists already
    if os.path.isfile(final_path) and os.path.getsize(final_path) > 0:
        logger.log(
            f"Skipping yt-dlp download, file already exists: {final_path}",
            status=logger.Status.INFO,
        )
        return self

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
        "hls_use_mpegts": True,
        "writesubtitles": True,
        "subtitleslangs": ["all"],
        "subtitlesformat": "srt",
        "ignoreerrors": True,
        "http_headers": self.headers,
        "concurrent_fragment_downloads": 15,
        # Let yt-dlp write to a temporary filename then move into place. Outtmpl uses unique pattern.
        "outtmpl": os.path.join(
            output_path, "{:02d}-{}.%(ext)s".format(int(video_index), str(title))
        ),
        "verbose": True if self.verbose > 0 else False,
        # allow resuming by enabling resume from partial files (yt-dlp will do this by default for many extractors)
        "continuedl": True,
    }

    # If ffmpeg is in a specific path, add it to the options
    if ffmpeg_path != "ffmpeg":
        ydl_opts["ffmpeg_location"] = ffmpeg_path

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # Use extract_info to get info_dict first (so we can check subtitles)
            try:
                info = ydl.extract_info(link, download=False)
            except Exception as ex_info:
                logger.log(
                    "extract_info failed (will try direct download). Error: %s"
                    + str(ex_info),
                    status=logger.Status.ERROR,
                )
                info = None

            if info:
                subs = info.get("subtitles") or info.get("automatic_captions") or {}
                if not subs:
                    logger.log(
                        "No subtitles metadata present for this video.",
                        status=logger.Status.INFO,
                    )
                else:
                    logger.log(
                        "Subtitles metadata keys: %s" + str(subs.keys()),
                        status=logger.Status.INFO,
                    )
            try:
                # Download (yt-dlp should attempt to resume partial downloads)
                ydl.download([link])
            except Exception as e:
                # If there's an HLS live fragment issue, log extra context
                logger.log(
                    "Could not download video '%s' (link=%s). Exception: %s"
                    + str(title)
                    + str(link)
                    + str(e),
                    status=logger.Status.ERROR,
                )

                logger.log(
                    "If you see 'Live HLS streams are not supported by the native downloader' warnings, "
                    "try re-running with CLI flags: --downloader ffmpeg --hls-use-mpegts or use subprocess fallback.",
                    status=logger.Status.WARNING,
                )
                # Re-raise so caller can decide (the caller code logs and moves on)
                raise

    except Exception as e_outer:
        # Final catch-all for unexpected errors (keep it informative)
        logger.log(
            f"download_video failed for title={title} index={video_index}: {e_outer}",
            status=logger.Status.ERROR,
        )
        raise
    return self
