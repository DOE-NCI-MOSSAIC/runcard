"""Allow ``python -m runcard``; the console script itself is ``runcard.cli.app:main``."""

from runcard.cli.app import main

if __name__ == "__main__":
    main()
