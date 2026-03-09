import triasApi
import logging


def extrapolateStopsWithClosestDelay(allStops):
    #make delayList
    extrapolatedStops = []
    for stop in allStops:
        thisCall = stop["CallAtStop"]
        ttbArr, estArr, ttbDep, estDep = getArrAndDepTimes(thisCall)
        extrapolatedStops.append({
            "estArr":      estArr,
            "ttbArr":      ttbArr,
            "estDep":      estDep,
            "ttbDep":      ttbDep,
            "notServiced": (thisCall.get("NotServicedStop") == "true"),
        })

    #fill out non serviced stops
    for stopIdx in range(len(extrapolatedStops)):
        processedStop = extrapolatedStops[stopIdx]
        if processedStop["notServiced"]:
            #try to find realtime data before current stop
            for beforeStopIdx in range(stopIdx-1,-1,-1):
                estDep = extrapolatedStops[beforeStopIdx]["estDep"]
                if estDep is None:
                    continue
                ttbDep = extrapolatedStops[beforeStopIdx]["ttbDep"]
                delayBefore = (estDep - ttbDep)
                break
            else:
                delayBefore = None

            #try to find realtime data after current stop
            for afterStopIdx in range(stopIdx+1, len(extrapolatedStops)):
                estArr = extrapolatedStops[afterStopIdx]["estArr"]
                if estArr is None:
                    continue
                ttbArr = extrapolatedStops[afterStopIdx]["ttbArr"]
                delayAfter = (estArr - ttbArr)
            else:
                delayAfter = None

            if (delayBefore is not None) and (delayAfter is not None):
                processedStop["intermediateNotServiced"] = True
            else:
                processedStop["intermediateNotServiced"] = False

            if delayBefore is not None:
                if processedStop["ttbArr"]:
                    processedStop["estArr"] = processedStop["ttbArr"] + delayBefore
                if processedStop["ttbDep"]:
                    processedStop["estDep"] = processedStop["ttbDep"] + delayBefore
            elif delayAfter is not None:
                if processedStop["ttbArr"]:
                    processedStop["estArr"] = processedStop["ttbArr"] + delayAfter
                if processedStop["ttbDep"]:
                    processedStop["estDep"] = processedStop["ttbDep"] + delayAfter
            else:
                return None
        else:
            if (processedStop["estArr"]) is None and (processedStop["estDep"] is None):
                return None
    return extrapolatedStops

def hasAnyRealtimeData(allStops):
    for stop in allStops:
        thisCall = stop["CallAtStop"]
        ttbArr, estArr, ttbDep, estDep = getArrAndDepTimes(thisCall)
        if (estArr is not None) or (estDep is not None):
            return True
    return False


def copy_www_to_webhost(local_path, remote_path = 'bwp@p0ng.de:/var/www/html/trias/'):
    for src_path in local_path.iterdir():
        scp_command = ['/run/current-system/sw/bin/scp', src_path, remote_path]
        try:
            subprocess.run(scp_command, check=True)
        except subprocess.CalledProcessError as e:
            logging.error(f"Error during file copy: {e}")
