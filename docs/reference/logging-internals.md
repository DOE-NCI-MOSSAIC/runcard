# Logging internals

How `runcard._logging` wires structlog to Hydra's stdlib handlers. Most
users never import from this module; `get_logger` is re-exported from the
package top level. It is documented here because the processor chain is what
decides what the console shows and what the JSON file keeps.

::: runcard._logging
