from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.teachable.teachable_downloader import TeachableDownloader

import yt_dlp

import src.helpers.logger as logger
from src.helpers.ffmpeg import check_ffmpeg_available, install_ffmpeg


def _target_video_path(output_path: str, title, video_index) -> str:
    return os.path.join(
        output_path, "{:02d}-{}.mp4".format(int(video_index), str(title))
    )


def download_with_yt_dlp(
    self: "TeachableDownloader", link: str, title, video_index, output_path
) -> bool:
    """
    Helper that attempts to download `link` using yt-dlp and returns True on success, False on failure.
    Designed to be safe to call from multiple places.
    """
    # Ensure output_path exists
    try:
        os.makedirs(output_path, exist_ok=True)
    except Exception:
        pass

    final_path = _target_video_path(output_path, title, video_index)
    if os.path.isfile(final_path) and os.path.getsize(final_path) > 0:
        logger.log(
            f"download_with_yt_dlp: file already exists, skipping: {final_path}",
            status=logger.Status.INFO,
        )
        return True

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
        "hls_use_mpegts": True,
        "writesubtitles": True,
        "subtitleslangs": ["all"],
        "subtitlesformat": "srt",
        "ignoreerrors": True,
        "http_headers": self.headers,
        "concurrent_fragment_downloads": 15,
        # Use an outtmpl that writes a temporary name in the folder then moves it to final name.
        "outtmpl": os.path.join(
            output_path, "{:02d}-{}.%(ext)s".format(int(video_index), str(title))
        ),
        "continuedl": True,
        "verbose": True if getattr(self, "verbose", 0) > 0 else False,
    }

    if ffmpeg_path != "ffmpeg":
        ydl_opts["ffmpeg_location"] = ffmpeg_path

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                # Try to probe info first to give better logs
                info = ydl.extract_info(link, download=False)
                if not info:
                    logger.log(
                        f"yt-dlp probe returned no info for link: {link}",
                        status=logger.Status.DEBUG,
                    )
            except Exception as ex_info:
                logger.log(
                    f"yt-dlp extract_info failed for link (will attempt direct download): {ex_info}",
                    status=logger.Status.DEBUG,
                )

            try:
                # download may raise; capture exceptions
                ydl.download([link])
            except Exception as e:
                logger.log(
                    f"yt-dlp download failed for {title} link={link} error={e}",
                    status=logger.Status.WARNING,
                )
                return False
    except Exception as e_outer:
        logger.log(
            f"download_with_yt_dlp unexpected error for title={title}: {e_outer}",
            status=logger.Status.ERROR,
        )
        return False

    # check final path presence
    if os.path.isfile(final_path) and os.path.getsize(final_path) > 0:
        logger.log(
            f"download_with_yt_dlp succeeded for: {final_path}",
            status=logger.Status.INFO,
        )
        return True

    # sometimes yt-dlp writes other extension - attempt to find matching file
    try:
        candidates = [
            f
            for f in os.listdir(output_path)
            if f.startswith("{:02d}-{}".format(int(video_index), str(title)))
        ]
        for c in candidates:
            cp = os.path.join(output_path, c)
            if os.path.isfile(cp) and os.path.getsize(cp) > 0:
                # if not .mp4, try rename
                if not cp.lower().endswith(".mp4"):
                    try:
                        os.rename(cp, final_path)
                        logger.log(
                            f"Renamed downloaded file {cp} -> {final_path}",
                            status=logger.Status.INFO,
                        )
                        return True
                    except Exception:
                        pass
                else:
                    return True
    except Exception:
        pass

    logger.log(
        f"download_with_yt_dlp could not find resulting file for title={title}",
        status=logger.Status.WARNING,
    )
    return False


# Keep original download_video for backward compatibility (returns self)
def download_video(
    self: "TeachableDownloader", link, title, video_index, output_path
) -> "TeachableDownloader":
    # Try to use the boolean helper and ignore result (backwards compatible)
    try:
        download_with_yt_dlp(self, link, title, video_index, output_path)
    except Exception:
        pass
    return self
