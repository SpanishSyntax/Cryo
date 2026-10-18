{
  description = "Cryo - Central Model Context Protocol (MCP) Store & Server Bridge for the SpanishSyntax Ecosystem";

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = {
    self,
    nixpkgs,
    flake-utils,
  }: let
    systems = flake-utils.lib.defaultSystems;
  in
    flake-utils.lib.eachSystem systems (system: let
      pkgs = import nixpkgs {inherit system;};
      lib = pkgs.lib;
      python = pkgs.python3;
      pythonPackages = pkgs.python3Packages;

      runtimeBins = with pkgs; [
        git
        nix
        direnv
        iproute2
        procps
        coreutils
        iputils
        ripgrep
        fd
        jq
        util-linux
        dnsutils
      ];

      cryoPackage = pythonPackages.buildPythonApplication {
        pname = "cryo";
        version = "0.1.0";
        src = lib.cleanSource ./.;
        pyproject = true;

        build-system = [
          pythonPackages.setuptools
        ];

        dependencies = [
          pythonPackages.mcp
        ];

        nativeBuildInputs = [
          pkgs.makeWrapper
        ];

        postFixup = ''
          wrapProgram $out/bin/cryo \
            --prefix PATH : ${lib.makeBinPath runtimeBins}
        '';

        pythonImportsCheck = [
          "cryo"
          "cryo.main"
          "cryo.ui"
          "cryo.tools"
          "cryo.tools.fs"
          "cryo.tools.git"
          "cryo.tools.system"
          "cryo.tools.docker"
          "cryo.tools.systemd"
          "cryo.tools.nixos"
          "cryo.tools.network"
          "cryo.tools.icebergs"
        ];

        doCheck = false;

        meta = with lib; {
          description = "Central Model Context Protocol (MCP) store & server bridge for the SpanishSyntax & Frost ecosystem";
          homepage = "https://github.com/SpanishSyntax/Cryo";
          license = licenses.mit;
          mainProgram = "cryo";
          platforms = platforms.unix;
        };
      };

      devPythonEnv = python.withPackages (ps:
        with ps; [
          mcp
          setuptools
          pytest
          ruff
        ]);
    in {
      packages = {
        default = cryoPackage;
        cryo = cryoPackage;
      };

      apps = {
        default = {
          type = "app";
          program = "${cryoPackage}/bin/cryo";
        };
        cryo = {
          type = "app";
          program = "${cryoPackage}/bin/cryo";
        };
      };

      devShells.default = pkgs.mkShell {
        packages = [
          devPythonEnv
          pkgs.uv
          pkgs.nil
          pkgs.nixd
          pkgs.nixfmt-rfc-style
          pkgs.git
          pkgs.direnv
        ];

        env = {
          UV_PYTHON = "${devPythonEnv}/bin/python3";
          UV_PYTHON_DOWNLOADS = "never";
        };

        shellHook = ''
          printf '\033[1;36m🧊 [cryo]\033[0m ⚡ \033[1mDevShell\033[0m (Python %s, uv %s, nil + nixd LSP) active\n' \
            "$(python3 --version | cut -d' ' -f2)" \
            "$(uv --version | cut -d' ' -f2)" >&2
        '';
      };
    })
    // {
      overlays = {
        default = final: prev: {
          cryo = self.packages.${prev.stdenv.hostPlatform.system}.default;
        };
        cryo = self.overlays.default;
      };

      nixosModules = {
        default = self.nixosModules.cryo;
        cryo = {
          config,
          lib,
          pkgs,
          ...
        }: let
          cfg = config.programs.cryo;
          system = pkgs.stdenv.hostPlatform.system;
        in {
          options.programs.cryo = {
            enable = lib.mkEnableOption "Cryo - Central Model Context Protocol (MCP) store & server bridge";
            package = lib.mkOption {
              type = lib.types.package;
              default = self.packages.${system}.default;
              description = "The Cryo package to install system-wide.";
            };
          };

          config = lib.mkIf cfg.enable {
            environment.systemPackages = [cfg.package];
          };
        };
      };

      homeManagerModules = {
        default = self.homeManagerModules.cryo;
        cryo = {
          config,
          lib,
          pkgs,
          ...
        }: let
          cfg = config.programs.cryo;
          tomlFormat = pkgs.formats.toml {};
          system = pkgs.stdenv.hostPlatform.system;
          defaultCryo = self.packages.${system}.default;
          mergedSettings =
            lib.recursiveUpdate
            (lib.optionalAttrs (cfg.packs != null || cfg.tools != null) {
              store =
                (lib.optionalAttrs (cfg.packs != null) { enabled_packs = cfg.packs; })
                // (lib.optionalAttrs (cfg.tools != null) { enabled_tools = cfg.tools; });
            })
            cfg.settings;
        in {
          options.programs.cryo = {
            enable = lib.mkEnableOption "Cryo - Central Model Context Protocol (MCP) store & server bridge";

            package = lib.mkOption {
              type = lib.types.package;
              default = defaultCryo;
              description = "The Cryo package to use.";
            };

            packs = lib.mkOption {
              type = lib.types.nullOr (lib.types.listOf lib.types.str);
              default = null;
              example = ["fs" "git" "system" "docker" "systemd" "nixos" "network"];
              description = "List of Cryo MCP capability packs to enable declaratively.";
            };

            tools = lib.mkOption {
              type = lib.types.nullOr (lib.types.listOf lib.types.str);
              default = null;
              example = ["ls" "cat" "grep" "git_status" "docker_ps" "journalctl"];
              description = "List of atomic MCP tools to enable declaratively.";
            };

            settings = lib.mkOption {
              type = tomlFormat.type;
              default = {};
              description = "Configuration written to ~/.config/cryo/cryo.toml when declarative mode is used.";
            };
          };

          config = lib.mkIf cfg.enable {
            home.packages = [cfg.package];
            xdg.configFile."cryo/cryo.toml" = lib.mkIf (mergedSettings != {}) {
              source = tomlFormat.generate "cryo.toml" mergedSettings;
            };
          };
        };
      };
    };
}
