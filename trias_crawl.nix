{ config, pkgs, lib, ... }:
let
  pythonEnv = pkgs.python3.withPackages (ps: with ps; [
    requests
    numpy
    svgpathtools
    xmltodict
    matplotlib
  ]);
in {
  
  users.users.pingu2.linger = true;
  systemd.user.services.trias-live-crawler = {
    description = "trias live crawler";
    serviceConfig = {
      ExecStart = "${pythonEnv}/bin/python /mnt/data/trias_crawl/main.py live";
      Restart = "on-failure";
      RestartSec = 120;
      StandardOutput = "journal";
      StandardError = "journal";
      Environment = "HOME=/home/pingu2";
    };
  };

  systemd.user.timers.trias-live-crawler = {
    description = "run trias live crawler every minute";
    timerConfig = {
      OnCalendar = "*:0/1";
      Persistent = true;
    };
    wantedBy = [ "timers.target" ];
  };

  systemd.user.services.trias-stat-crawler = {
    description = "trias stat crawler";
    serviceConfig = {
      ExecStart = "${pythonEnv}/bin/python /mnt/data/trias_crawl/main.py stat";
      Restart = "on-failure";
      RestartSec = 120;
      StandardOutput = "journal";
      StandardError = "journal";
      Environment = "HOME=/home/pingu2";
    };
  };

  systemd.user.timers.trias-stat-crawler = {
    description = "run trias stat crawler every 30 minutes";
    timerConfig = {
      OnCalendar = "*:0/30";
      Persistent = true;
    };
    wantedBy = [ "timers.target" ];
  };


}
