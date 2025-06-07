{
  description = "Development Nix flake for OpenAI Codex CLI";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
      flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { nixpkgs, flake-utils, ... }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs {
          inherit system;
        };
        monorepo-deps = with pkgs; [
          # for precommit hook
          pnpm
          husky
        ];
        codex-cli = import ./codex-cli {
          inherit pkgs monorepo-deps;
        };
      in
      rec {
        packages = {
          codex-cli = codex-cli.package;
        };

        devShells = {
          codex-cli = codex-cli.devShell;
        };

        apps = {
          codex-cli = codex-cli.app;
        };

        defaultPackage = packages.codex-cli;
        defaultApp = apps.codex-cli;
        defaultDevShell = devShells.codex-cli;
      }
    );
}
