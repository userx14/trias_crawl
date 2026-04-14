import crawler
import visualizeMap
import visualizeGraph
import logging
from pathlib import Path
from datetime import datetime, timedelta
import traceback
import subprocess

base_dir = Path(__file__).parent
www_dir  = base_dir/'www'
remote_webroot = 'bwp@p0ng.de:/var/www/html/trias/'
"""
try:
    crawler.getDelayData()
except Exception:
    logging.error("Error during data crawling:\n%s", traceback.format_exc())
"""
try:
    visualizeMap.render_liveMap(www_dir/"currentRunningTrains.json", base_dir/"svg_source/live_map_source_light.svg", www_dir/"live_map.svg")
    visualizeMap.render_liveMap(www_dir/"currentRunningTrains.json", base_dir/"svg_source/live_map_source_dark.svg", www_dir/"live_map_dark.svg")
except Exception:
    logging.error("Error during live map rendering:\n%s", traceback.format_exc())

try:
    visualizeGraph.render_liveGraph(www_dir/"currentRunningTrains.json", www_dir/"live_graph.svg")
except Exception:
    logging.error("Error during live map rendering:\n%s", traceback.format_exc())

try:
    now       = datetime.now()
    timeRangeDict = {
        "today": (now, now),
        "yesterday": (now+timedelta(days=-1), now+timedelta(days=-1)),
        "lastWeek": (now+timedelta(days=-7), now)
    }

    for timeRangeName, timeRange in timeRangeDict.items():
        delMapSource = base_dir / "svg_source" / "stat_map_delay_light.svg"
        visualizeMap.render_delayStatMap(*timeRange, delMapSource, www_dir/f"stat_map_delay_{timeRangeName}.svg")

        nosMapSource = base_dir / "svg_source" / "stat_map_notServ_light.svg"
        visualizeMap.render_nonServStatMap(*timeRange, nosMapSource, www_dir/f"stat_map_nonServ_{timeRangeName}.svg")

        deltaDMapSource = base_dir / "svg_source" / "stat_map_delayChange_light.svg"
        visualizeMap.render_delayChangeMap(*timeRange, deltaDMapSource, www_dir/f"stat_map_delaySection_{timeRangeName}.svg")

        numTrainsSource = base_dir / "svg_source" / "stat_map_numTrains_light.svg"
        visualizeMap.render_numberOfTrainsMap(*timeRange, numTrainsSource, www_dir/f"stat_map_numTrains_{timeRangeName}.svg")

except Exception:
    logging.error("Error during stat map rendering:\n%s", traceback.format_exc())
"""
#upload
for src_path in www_dir.iterdir():
    scp_command = ['/run/current-system/sw/bin/scp', src_path, remote_webroot]
    try:
        subprocess.run(scp_command, check=True)
    except subprocess.CalledProcessError as e:
        logging.error(f"Error during file copy: {e}")
"""
