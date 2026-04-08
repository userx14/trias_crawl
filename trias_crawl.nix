{ config, pkgs, lib, ... }:
let
  pythonEnv = pkgs.python3.withPackages (ps: with ps; [
    requests
    numpy
    svgpathtools
    xmltodict
  ]);
in {
  
  users.users.pingu2.linger = true;
  systemd.user.services.trias-crawler = {
    description = "Trias crawler";
    serviceConfig = {
      ExecStart = "${pythonEnv}/bin/python /mnt/data/trias_crawl/main.py";
      Restart = "on-failure";
      RestartSec = 120;
      StandardOutput = "journal";
      StandardError = "journal";
      Environment = "HOME=/home/pingu2";
    };
  };

  systemd.user.timers.trias-crawler = {
    description = "run Trias crawler every 5 minutes";
    timerConfig = {
      OnCalendar = "*:0/5";
      Persistent = true;
    };
    wantedBy = [ "timers.target" ];
  };
}
