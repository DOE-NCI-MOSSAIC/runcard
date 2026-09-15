{
  description = "runcard dev shell";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs { inherit system; };
        # Python version to match what OLCF miniforge3 provides
        python = pkgs.python312;
      in
      {
        devShells.default = pkgs.mkShell {
          name = "runcard";

          buildInputs = [
            python
            pkgs.uv
            pkgs.just
            pkgs.git
          ];

          shellHook = ''
            echo "runcard dev shell"
            echo "  python : $(python3 --version)"
            echo "  uv     : $(uv --version)"
            echo ""
            # Return to the user's shell (nix develop forces bash)
            _user_shell=$(grep "^$USER:" /etc/passwd | cut -d: -f7) || true
            [ -x "''${_user_shell:-}" ] && [ "''${_user_shell##*/}" != bash ] && exec "$_user_shell"
          '';

          # Ensure UV doesn't fight with Nix's Python
          env = {
            UV_PYTHON_PREFERENCE = "only-system";
          };
        };
      }
    );
}
