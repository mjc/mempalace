{
  description = "Development shell for MemPalace";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs { inherit system; };
        python = pkgs.python313;
      in
      {
        devShells.default = pkgs.mkShell {
          packages = with pkgs; [
            python
            python313Packages.pip
            python313Packages.setuptools
            python313Packages.wheel
            python313Packages.virtualenv
            uv
            git
          ] ++ pkgs.lib.optionals pkgs.stdenv.isLinux [
            pkgs.stdenv.cc.cc.lib
          ];

          LD_LIBRARY_PATH = pkgs.lib.makeLibraryPath [
            pkgs.stdenv.cc.cc.lib
          ];
          PIP_DISABLE_PIP_VERSION_CHECK = "1";

          shellHook = ''
            export MEMPALACE_DEFAULT_VENV="''${MEMPALACE_DEFAULT_VENV:-.venv}"
            echo "MemPalace dev shell"
            echo "Python: $(python --version)"
            echo "Bootstrap: python -m venv $MEMPALACE_DEFAULT_VENV && source $MEMPALACE_DEFAULT_VENV/bin/activate"
            echo "Deps: pip install -e '.[dev]'"
            echo "Alt: uv sync --group dev"
          '';
        };
      });
}
