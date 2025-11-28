from __future__ import annotations

import sys

import src.helpers.logger as logger
from src.helpers.file_helper import read_urls_from_file
from src.teachable.teachable_downloader import TeachableDownloader
from src.utils.startup_arguments import get_startup_arguments

if __name__ == "__main__":
    args = get_startup_arguments()
    downloader = TeachableDownloader(args=args)
    if args.file_urls_path:
        urls = read_urls_from_file(args.file_urls_path)
        try:
            downloader.run_batch(urls, args.email, args.login_url)
            downloader.clean_up()
            sys.exit(0)
        except KeyboardInterrupt:
            logger.log("Interrupted by user", status=logger.Status.ERROR)
            downloader.clean_up()
            sys.exit(1)
        except Exception as e:
            logger.log(f"Error: {e}", status=logger.Status.ERROR)
            downloader.clean_up()
            sys.exit(1)
    else:
        # Check if url argument is passed
        if not args.url:
            logger.log("URL is required", status=logger.Status.ERROR)
            sys.exit(1)
        try:
            downloader.run(
                course_url=args.url,
                email=args.email,
                login_url=args.login_url,
            )
            downloader.clean_up()
            sys.exit(0)
        except KeyboardInterrupt:
            logger.log("Interrupted by user", status=logger.Status.ERROR)
            downloader.clean_up()
            sys.exit(1)
        except Exception as e:
            logger.log(f"Error: {e}", status=logger.Status.ERROR)
            downloader.clean_up()
            sys.exit(1)
