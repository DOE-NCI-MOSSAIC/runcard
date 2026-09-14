# Compatibility shim for nix-shell on systems where nix develop fails
# (e.g. Frontier via nix-portable — nested mount namespaces are blocked)
(builtins.getFlake (toString ./.)).devShells.${builtins.currentSystem}.default
