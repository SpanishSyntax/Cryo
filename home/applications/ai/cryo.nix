{
  pkgs,
  config,
  lib,
  inputs,
  ...
}: let
  cfg = config.frost.home.apps.ai.cryo;
  system = pkgs.stdenv.hostPlatform.system;
  defaultPackage = inputs.cryo.packages.${system}.default;

  mcpHubSpec = {
    command = "${cfg.package}/bin/cryo";
    args = ["serve"];
  };
in {
  options.frost.home.apps.ai.cryo = {
    enable = lib.mkEnableOption "Cryo central MCP server bridge";

    package = lib.mkOption {
      type = lib.types.package;
      default = defaultPackage;
      defaultText = lib.literalExpression "inputs.cryo.packages.\${pkgs.stdenv.hostPlatform.system}.default";
      description = "The Cryo package built from the cryo flake input.";
    };

    exportToMcpHub = lib.mkOption {
      type = lib.types.str;
      readOnly = true;
      default = builtins.toJSON mcpHubSpec;
      description = ''
        JSON snippet for registering Cryo with Antigravity, OpenCode, and Claude Desktop:
        {
          "command": "''${inputs.cryo.packages.''${pkgs.stdenv.hostPlatform.system}.default}/bin/cryo",
          "args": ["serve"]
        }
      '';
    };

    mcpServerAttr = lib.mkOption {
      type = lib.types.attrsOf lib.types.anything;
      readOnly = true;
      default = mcpHubSpec;
      description = "Nix attribute set representation of `exportToMcpHub` for direct Nix composition.";
    };
  };

  config = lib.mkIf cfg.enable {
    home.packages = [
      cfg.package
    ];
  };
}
