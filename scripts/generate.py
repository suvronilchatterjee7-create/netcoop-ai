"""Generate the labelled dataset (wrapper around ``netcoop generate``)."""

import sys

from netcoop.cli.main import main

if __name__ == "__main__":
    sys.exit(main(["generate", *sys.argv[1:]]))
