from datetime import datetime, timezone, timedelta
from pathlib import Path
import logging
import json
import subprocess
import traceback
import xmltodict

import triasApi

base_dir      = Path(__file__).parent

triasApi.requestorKey = open(base_dir/"requestor.key").read()

logging.basicConfig(
    filename=base_dir/"error.log",
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s'
)

def getLiveJourney(serviceData, allStops, extrapolatedStops, currentTime, liveJourneyDict):
    for currentStopIdx in range(len(extrapolatedStops)-2, 0, -1): #exclude first stop
        processedStop = extrapolatedStops[currentStopIdx]
        if processedStop["estDep"] < currentTime:
            #train left this station and is on the way to the next
            progressToNextStop = None #still needs to be calculated
            delay = processedStop["estDep"] - processedStop["ttbDep"]
            break
            #find next station

        elif processedStop["estArr"] < currentTime:
            #train is at this station
            progressToNextStop = 0.0
            delay = processedStop["estArr"] - processedStop["ttbArr"]
            break
    else:
        if processedStop["estDep"] < currentTime:
            #train left this station and is on the way to the next
            progressToNextStop = None #still needs to be calculated
        else:
            progressToNextStop = 0.0
        delay = processedStop["estDep"] - processedStop["ttbDep"]
    delay = delay.total_seconds()
    cancelled = False
    if extrapolatedStops[currentStopIdx]["notServiced"]:
        if not extrapolatedStops[currentStopIdx]["intermediateNotServiced"]:
            cancelled = True
    #find next valid stop
    for nextStopIdx in range(currentStopIdx+1, len(extrapolatedStops)):
        if extrapolatedStops[nextStopIdx]["notServiced"]:
            if not extrapolatedStops[nextStopIdx]["intermediateNotServiced"]:
                cancelled = True
            else:
                continue
        break
    if progressToNextStop is None:
        progressToNextStop = currentTime - extrapolatedStops[currentStopIdx]["estDep"]
        progressToNextStop /= extrapolatedStops[nextStopIdx]["estArr"] - extrapolatedStops[currentStopIdx]["estDep"]

    currentStopName = allStops[currentStopIdx]["CallAtStop"]["StopPointName"]["Text"]
    currentStopRef  = allStops[currentStopIdx]["CallAtStop"]["StopPointRef"]
    nextStopName    = allStops[nextStopIdx]["CallAtStop"]["StopPointName"]["Text"]
    nextStopRef     = allStops[nextStopIdx]["CallAtStop"]["StopPointRef"]

    if serviceData.get("Unplanned") == "true":
        logging.error("Unplanned train :)")
    if serviceData.get("Deviation") == "true":
        logging.error("Deviated train :)")

    liveJourney = {
        "delay":            delay / 60,
        "lineName":         serviceData["ServiceSection"]["PublishedLineName"]["Text"],
        "incidentText":     triasApi.getIncidentText(serviceData),
        "currentStopName":  currentStopName,
        "currentStopRef":   currentStopRef,
        "nextStopName":     nextStopName,
        "nextStopRef":      nextStopRef,
        "destination":      serviceData["DestinationText"]["Text"],
        "origin":           serviceData["OriginText"]["Text"],
        "progressNextStop": progressToNextStop,
        "cancelled":        cancelled
    }

    trainJourneyRef  = serviceData["JourneyRef"]
    operatingDayRef  = triasApi.datetimeFromTriasDateStr(serviceData["OperatingDayRef"]).strftime("%Y.%m.%d")
    if not any([trainJourneyRef in iterRef for iterRef in liveJourneyDict.keys()]): #block duplicating journey around midnight
        liveJourneyDict[trainJourneyRef+":"+operatingDayRef] = liveJourney

def acquireTrainLineFilter(lineName):
    if "S" in lineName:
        return True
    return False

def combineAllStops(stopEvent):
    allStopsUnfiltered = []
    for callCat in ["PreviousCall", "ThisCall", "OnwardCall"]:
        stopOrStopsList = stopEvent["StopEvent"].get(callCat)
        if stopOrStopsList is not None:
            allStopsUnfiltered.extend(stopOrStopsList)

    #remove stops with identical stopPointRef, and fix indices
    duplicateCount = 0
    allStops = [allStopsUnfiltered[0]]
    for stopIdx in range(1, len(allStopsUnfiltered)):
        if allStopsUnfiltered[stopIdx]["CallAtStop"]["StopPointRef"] == allStops[-1]["CallAtStop"]["StopPointRef"]:
            duplicateCount += 1
            continue
        allStops.append(allStopsUnfiltered[stopIdx])
        seqNr = int(allStops[-1]["CallAtStop"]["StopSeqNumber"])
        allStops[-1]["CallAtStop"]["StopSeqNumber"] = str(seqNr - duplicateCount)
    return allStops

def fillInEstimates(allStops):
    #make delayList
    extrapolatedStops = []
    for stop in allStops:
        thisCall = stop["CallAtStop"]
        ttbArr, estArr, ttbDep, estDep = triasApi.getArrAndDepTimes(thisCall)
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
                raise ValueError("missing live data")
        else:
            if (processedStop["estArr"]) is None and (processedStop["estDep"] is None):
                raise ValueError("missing live data")
    return extrapolatedStops

def hasAnyLiveData(allStops):
    for stop in allStops:
        thisCall = stop["CallAtStop"]
        ttbArr, estArr, ttbDep, estDep = triasApi.getArrAndDepTimes(thisCall)
        if (estArr is not None) or (estDep is not None):
            return True
    return False



def getAllDelaysThroughStation(stationName, stationRef, liveJourneysDict):
    stopEventResponse = triasApi.getStopEvents(stationName, stationRef, numResults=100)
    responseTimestampStr, calculationTimeMs = triasApi.getResponseStatistics(stopEventResponse)

    liveJourneysDict["info"]["responseTimestamp"] = responseTimestampStr
    liveJourneysDict["info"]["calculationTimeMs"] += calculationTimeMs
    serviceDelivery = stopEventResponse["Trias"]["ServiceDelivery"]
    
    toEarly = 0
    toLate  = 0
    noData  = 0
    error   = 0
    good    = 0

    for stopEvent in serviceDelivery["DeliveryPayload"]["StopEventResponse"]["StopEventResult"]:
        try:
            serviceData      = stopEvent["StopEvent"]["Service"]
            trainLine        = serviceData["ServiceSection"]["PublishedLineName"]["Text"]
            if not acquireTrainLineFilter(trainLine):
                continue
            trainJourney     = serviceData["JourneyRef"]
            trainOrigin      = serviceData["OriginText"]["Text"]
            trainDestination = serviceData["DestinationText"]["Text"]
            logging.debug(f"{trainLine} ({trainJourney}) from {trainOrigin} to {trainDestination}")

            #check if the journey has already started
            allStops          = combineAllStops(stopEvent)
            journeyStartTime  = arrivalDictallStops[-1]["ServiceDeparture"]["TimetabledTime"]
            journeyStartTime  = triasApi.datetimeFromTriasDatetimeStr(journeyStartTime)
            if currentTime < journeyStartTime:
                toEarly += 1
                continue

            if not hasAnyLiveData(allStops):
                noData += 1
                continue

            #check if the journey has already ended
            extrapolatedStops = fillInEstimates(allStops)
            if extrapolatedStops[-1]["estArr"] < currentTime:
                toLate += 1
                continue

            getLiveJourney(serviceData, allStops, extrapolatedStops, currentTime, liveJourneysDict["journeys"])
            good += 1
        except Exception as e:
            error += 1
            logging.error(traceback.format_exc())
    logging.info(f"statistic for {passingThroughName}: good: {good}, early: {toEarly}, late: {toLate}, no data: {noData}, error: {error}")

def copy_www_to_webhost(local_path, remote_path = 'bwp@p0ng.de:/var/www/html/trias/'):
    for src_path in local_path.iterdir():
        scp_command = ['/run/current-system/sw/bin/scp', src_path, remote_path]
        try:
            subprocess.run(scp_command, check=True)
        except subprocess.CalledProcessError as e:
            logging.error(f"Error during file copy: {e}")

def getCurrentRunningTrains():
    checkAtStations = [
        ('Zuffenhausen',       'de:08111:6465'),
        ('Vaihingen',          'de:08111:6002'),
        ('Ludwigsburg',        'de:08118:7402'),
        ('Renningen',          'de:08115:7302'),
        ('Böblingen',          'de:08115:7100'),
        ('Bad Cannstatt',      'de:08111:6333'),
        ('Schwabstraße',       'de:08111:6052'),
        ('Waiblingen',         'de:08119:7604'),
        ('Esslingen (Neckar)', 'de:08116:7800'),
    ]

    allLiveJourneys = {"info": {"calculationTimeMs": 0, "responseTimestamp": None}, "journeys": dict()}
    for stationTuple in checkAtStations:
        logging.info(f"station {stationTuple[0]}")
        getAllDelaysThroughStation(*stationTuple, allLiveJourneys)
    allLiveJourneys["info"]["attachedDataFormatRevision"] = "2026.02.26"
    allLiveJourneys["info"]["license"]                    = "DL-DE/BY-2-0"
    allLiveJourneys["info"]["rawDataSourceUrl"]           = "https://mobidata-bw.de/dataset/trias"
    allLiveJourneys = dict(sorted(allLiveJourneys.items()))
    return allLiveJourneys

def main():
    try:
        #get trias data
        allLiveJourneys = getCurrentRunningTrains()

        #write live data into json
        with open(base_dir/"www/currentRunningTrains.json", "w") as outputfile:
            outputfile.write(json.dumps(allLiveJourneys, indent=4))

        #render livemap
        www_dir = base_dir/'www'
        try:
            from visualize_liveMap import render_liveMap
            render_liveMap(www_dir/"currentRunningTrains.json", base_dir/"svg_source"/"live_map_source_light.svg", www_dir/"live_map.svg")
        except Exception as e:
            logging.exception("Failed to update live map")

        #upload
        copy_www_to_webhost(www_dir)
    except Exception:
        logging.error("Unhandled exception:\n%s", traceback.format_exc())
        raise


if __name__ == "__main__":
    main()
