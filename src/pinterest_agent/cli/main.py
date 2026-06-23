"""Click root CLI group.

Commands are registered in separate modules that import ``cli`` and decorate it.

Logging is configured once at CLI startup from the config file (if available).
"""

from __future__ import annotations

import logging
import os

import click

from pinterest_agent import __version__
from pinterest_agent.config.loader import ConfigLoader
from pinterest_agent.utils.logging_setup import setup_logging

logger = logging.getLogger(__name__)


@click.group(
    help="Pinterest Aesthetic Automation — generate and publish Pinterest-optimized images.",
    epilog=(
        "Examples:\n\n"
        "  pinterest-agent generate-prompts --niche old_money --count 10\n"
        "  pinterest-agent generate-images --count 5\n"
        "  pinterest-agent publish-pins --count 3\n"
        "  pinterest-agent status\n"
        "  pinterest-agent stats --days 30\n"
        "  pinterest-agent doctor --fix\n"
    ),
)
@click.version_option(
    version=__version__,
    message="%(prog)s v%(version)s",
)
def cli() -> None:
    """Pinterest Aesthetic Automation — generate and publish Pinterest-optimized images."""
    _init_logging()


def _init_logging() -> None:
    """Attempt to configure structured logging from the config file.

    Falls back gracefully to basic INFO logging if the config file
    is missing or unreadable.
    """
    config_path = os.getenv("PINTEREST_CONFIG", "config.yaml")
    try:
        loader = ConfigLoader(config_path)
        config = loader.load(config_path)
        setup_logging(config.logging)
    except Exception:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        )


@cli.command()
def version() -> None:
    """Print the installed version and exit."""
    from pinterest_agent import __version__

    click.echo(f"pinterest-agent v{__version__}")


# ------------------------------------------------------------------
# Register sub-commands by importing their modules
# ------------------------------------------------------------------
# Each module imports ``cli`` from this module and attaches commands
# via decorators. Importing the module triggers the registration.

import pinterest_agent.cli.generate  # noqa: F811, E402  - registers generate-prompts, list-prompts, retry-prompts, generate-images, list-images, retry-images
import pinterest_agent.cli.publish  # noqa: F811, E402  - registers publish-pins, list-publications, retry-publications, scheduler-run
import pinterest_agent.cli.config_cmd  # noqa: F811, E402  - registers show-config, validate-config, reload-config
import pinterest_agent.cli.status_cmd  # noqa: F811, E402  - registers status
import pinterest_agent.cli.stats_cmd  # noqa: F811, E402  - registers stats
import pinterest_agent.cli.doctor_cmd  # noqa: F811, E402  - registers doctor
