import crawler
import visualizeSvg
import logging
from pathlib import Path
from datetime import datetime, timedelta
import traceback
import subprocess

base_dir = Path(__file__).parent
www_dir  = base_dir/'www'
remote_webroot = 'bwp@p0ng.de:/var/www/html/trias/'

try:
    crawler.getDelayData()
except Exception:
    logging.error("Error during data crawling:\n%s", traceback.format_exc())

try:
    visualizeSvg.render_liveMap(www_dir/"currentRunningTrains.json", base_dir/"svg_source/live_map_source_light.svg", www_dir/"live_map.svg")
    visualizeSvg.render_liveMap(www_dir/"currentRunningTrains.json", base_dir/"svg_source/live_map_source_dark.svg", www_dir/"live_map_dark.svg")
except Exception:
    logging.error("Error during live map rendering:\n%s", traceback.format_exc())

try:
    now       = datetime.now()
    yesterday = now+timedelta(days=-1)

    delMapSource = base_dir / "svg_source" / "stat_map_delay_light.svg"
    visualizeSvg.render_delayStatMap(now, now,                    delMapSource, www_dir/"stat_map_delay_today.svg")
    visualizeSvg.render_delayStatMap(yesterday, yesterday,        delMapSource, www_dir/"stat_map_delay_yesterday.svg")
    visualizeSvg.render_delayStatMap(now+timedelta(days=-7), now, delMapSource, www_dir/"stat_map_delay_lastWeek.svg")

    nosMapSource = base_dir / "svg_source" / "stat_map_notServ_light.svg"
    visualizeSvg.render_nonServStatMap(now, now,                    nosMapSource, www_dir/"stat_map_nonServ_today.svg")
    visualizeSvg.render_nonServStatMap(yesterday, yesterday,        nosMapSource, www_dir/"stat_map_nonServ_yesterday.svg")
    visualizeSvg.render_nonServStatMap(now+timedelta(days=-7), now, nosMapSource, www_dir/"stat_map_nonServ_lastWeek.svg")

    deltaDMapSource = base_dir / "svg_source" / "stat_map_delayChange_light.svg"
    visualizeSvg.render_delaySectionMap(now, now, deltaDMapSource, www_dir/"stat_map_delaySection_today.svg")
    visualizeSvg.render_delaySectionMap(yesterday, yesterday, deltaDMapSource, www_dir/"stat_map_delaySection_yesterday.svg")
    visualizeSvg.render_delaySectionMap(now+timedelta(days=-7), now, deltaDMapSource, www_dir/"stat_map_delaySection_lastWeek.svg")


except Exception:
    logging.error("Error during stat map rendering:\n%s", traceback.format_exc())

#upload
for src_path in www_dir.iterdir():
    scp_command = ['/run/current-system/sw/bin/scp', src_path, remote_webroot]
    try:
        subprocess.run(scp_command, check=True)
    except subprocess.CalledProcessError as e:
        logging.error(f"Error during file copy: {e}")
