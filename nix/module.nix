self:
{
  config,
  lib,
  pkgs,
  ...
}:

let
  cfg = config.services.bambu-plotter;
in
{
  options.services.bambu-plotter = {
    enable = lib.mkEnableOption "Bambu Plotter";
    package = lib.mkOption {
      type = lib.types.package;
      default = self.packages.${pkgs.stdenv.hostPlatform.system}.default;
      defaultText = lib.literalExpression "bambu-plotter.packages.\${system}.default";
    };
    host = lib.mkOption {
      type = lib.types.str;
      default = "127.0.0.1";
      description = "Address to listen on. The page has no login, so keep it private.";
    };
    port = lib.mkOption {
      type = lib.types.port;
      default = 8000;
    };
  };

  config = lib.mkIf cfg.enable {
    # Printer IP, serial, access code, calibration and the last upload live
    # in /var/lib/bambu-plotter.
    systemd.services.bambu-plotter = {
      description = "Bambu Plotter";
      wantedBy = [ "multi-user.target" ];
      wants = [ "network-online.target" ];
      after = [ "network-online.target" ];
      environment.BAMBU_PLOTTER_CONFIG = "/var/lib/bambu-plotter/settings.json";
      serviceConfig = {
        ExecStart = "${lib.getExe cfg.package} --host ${cfg.host} --port ${toString cfg.port}";
        DynamicUser = true;
        StateDirectory = "bambu-plotter";
        Restart = "on-failure";
        RestartSec = 5;
        ProtectSystem = "strict";
        ProtectHome = true;
        PrivateTmp = true;
        NoNewPrivileges = true;
      };
    };
  };
}
