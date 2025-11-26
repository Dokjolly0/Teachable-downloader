import src.helpers.logger as logger
from src.utils.startup_arguments import get_startup_arguments

if __name__ == "__main__":
    startup_arguments = get_startup_arguments()
    logger.log(str(startup_arguments), status=logger.Status.INFO)
