from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, asdict
from pathlib import Path
import logging
import json
import subprocess
import traceback
import xmltodict
import datetime
import triasApi
import crawl_helperFunc

@dataclasses.dataclass
class Stop:
    stopPointName: str
    stopPointRef: str
    stopIndex: int
    departureTimetable: datetime.datetime
    departureEstimate: datetime.datetime
    arrivalTimetable: datetime.datetime
    arrivalEstimate: datetime.datetime
    isNotServiced: bool

    def __init__(self, stopCall, stopIndexOffset = 0):
        self.stopPointName = stopCall["StopPointName"]["Text"]
        self.stopPointRef = thisCall["StopPointRef"]
        self.stopIndex = int(thisCall["StopSeqNumber"]) + stopIndexOffset

        arrival = stopCall.get("ServiceArrival")
        if arrival is not None:
            self.arrivalTimetable = triasApi.datetimeFromTriasDatetimeStr(arrival["TimetabledTime"])
            self.arrivalEstimate = arrival.get("EstimatedTime")
            self.arrivalEstimate = triasApi.datetimeFromTriasDatetimeStr(self.arrivalEstimate)

        departure = stopCall.get("ServiceDeparture")
        if departure is not None:
            self.departureTimetable = triasApi.datetimeFromTriasDatetimeStr(departure["TimetabledTime"])
            self.departureEstimate = departure.get("EstimatedTime")
            self.departureEstimate = triasApi.datetimeFromTriasDatetimeStr(self.departureEstimate)

        self.isNotServiced = (thisCall.get("NotServicedStop") == "true")


@dataclasses.dataclass
class Journey:
    journeyRef:   str
    operatingDay: datetime.datetime
    lineName:     str
    origin:       str
    destination:  str
    incidentText: str
    isCancelled:  bool
    isUnplanned:  bool
    isDeviated:   bool
    stops:        List[Stop]

    def __init__(self, stopEvent):
        serviceData      = stopEvent["StopEvent"]["Service"]

        self.journeyRef   = serviceData["JourneyRef"]
        self.origin       = serviceData["OriginText"]["Text"]
        self.destination  = serviceData["DestinationText"]["Text"]
        self.operatingDay = serviceData["OperatingDayRef"]
        self.operatingDay = triasApi.datetimeFromTriasDateStr(self.operatingDay)
        #process line name
        self.lineName = serviceData["ServiceSection"]["PublishedLineName"]["Text"]
        if self.lineName.startswith("S"):
            raise ValueError("Not an S-Bahn Line")


        #process incidentText
        stopEventAttribs = serviceData.get("Attribute")
        if stopEventAttribs is not None:
            for att in stopEventAttribs:
                if "Incident" in att["Code"]:
                    self.incidentText = att["Text"]["Text"]
                    break

        #process all stops
        allStopCalls = []
        for callCat in ["PreviousCall", "ThisCall", "OnwardCall"]:
            stopOrStopsList = stopEvent["StopEvent"].get(callCat)
            if stopOrStopsList is not None:
                allStopCalls.extend(stopOrStopsList)

        stopIndexOffset = 0
        for stopCall in allStopCalls:
            s = Stop(stopCall["CallAtStop"])
            if self.stops and s.stopPointRef == self.stops[-1].stopPointRef:
                stopIndexOffset -= 1
                continue
            self.stops.append(s)

        #process booleans
        self.isCancelled = (serviceData.get("Cancelled") == "true")
        self.isUnplanned = (serviceData.get("Unplanned") == "true")
        self.isDeviated  = (serviceData.get("Deviation") == "true")




@dataclasses.dataclass
class LiveJourney:
    journeyRef:   str
    lineName:         str
    origin:           str
    destination:      str
    delayMinutes:     int
    incidentText:     str
    currentStopName:  str
    currentStopRef:   str
    progressNextStop: str
    nextStopName:     str
    nextStopRef:      str
    isCancelled:      bool

    def __init__(self, journey: Journey, evaluationTime: datetime.datetime):
        #check for realtime data availability
        for stop in jorney.stops:
            if stop.departureEstimate or stop.arrivalEstimate:
                break
        else:
            raise ValueError("Not a single station with realtime data found")

        #extrapolate realtime data
        for stopIdx, stop in enumerate(jorney.stops):
            if stop.departureTimetable and not stop.departureEstimate:
                #need to extrapolate, search forward
                for range(stopIdx)
            if stop.arrivalTimetable and not stop.arrivalEstimate:
                #need to extrapolate
                break


        self.journeyRef = journey.journeyRef
        self.lineName = journey.lineName
        self.origin = journey.origin
        self.destination = journey.destination
        self.incidentText = journey.incidentText


        self.currentStopName  =
        self.currentStopRef   =
        self.progressNextStop =
        self.nextStopName     =
        self.nextStopRef      =
        self.isCancelled      =
        self.delayMinutes     =


    def as_dict():
        liveJourneyDict = dataclasses.asdict(self)
        journeyRef = liveJourneyDict.pop("journeyRef")
        return {journeyRef: liveJourneyDict}


            extrapolatedStops = crawl_helperFunc.extrapolateStopsWithClosestDelay(allStops)
            if extrapolatedStops is None:
                error += 1
                continue

            #check if the journey has already started
            if currentTime < extrapolatedStops[0]["ttbDep"]:
                toEarly += 1
                continue

            #check if the journey has already ended
            if extrapolatedStops[-1]["estArr"] < currentTime:
                toLate += 1
                continue

            getLiveJourney(serviceData, allStops, extrapolatedStops, currentTime, liveJourneysDict)
            good += 1
        except Exception as e:
            error += 1
            logging.error(traceback.format_exc())


base_dir = Path(__file__).parent
triasApi.requestorKey = open(base_dir/"requestor.key").read()
logging.basicConfig(
    #filename=base_dir/"error.log",
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s'
)

def getLiveJourney(serviceData, allStops, extrapolatedStops, currentTime, outputDict):
    for currentStopIdx in range(len(extrapolatedStops)-2, 0, -1): #exclude first and last stop
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
            #train left first station and is on the way to the next
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
        timeBetweenStops   = extrapolatedStops[nextStopIdx]["estArr"] - extrapolatedStops[currentStopIdx]["estDep"]
        if timeBetweenStops == 0:
            logging.warning("zero travel time between stops")
            progressToNextStop = 0.0
        else:
            progressToNextStop /= timeBetweenStops

    liveJourney = {
        "delay":            delay / 60,
        "lineName":         serviceData["ServiceSection"]["PublishedLineName"]["Text"],
        "incidentText":     crawl_helperFunc.getIncidentText(serviceData),
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
    outputDict["journeys"][trainJourneyRef] = liveJourney


def getAllDelaysThroughStation(stationName, stationRef, liveJourneysDict):



            if not crawl_helperFunc.hasAnyRealtimeData(allStops):
                noData += 1
                continue

            extrapolatedStops = crawl_helperFunc.extrapolateStopsWithClosestDelay(allStops)
            if extrapolatedStops is None:
                error += 1
                continue

            #check if the journey has already started
            if currentTime < extrapolatedStops[0]["ttbDep"]:
                toEarly += 1
                continue

            #check if the journey has already ended
            if extrapolatedStops[-1]["estArr"] < currentTime:
                toLate += 1
                continue

            getLiveJourney(serviceData, allStops, extrapolatedStops, currentTime, liveJourneysDict)
            good += 1
        except Exception as e:
            error += 1
            logging.error(traceback.format_exc())
    logging.info(f"statistic for {stationName}: good: {good}, early: {toEarly}, late: {toLate}, no data: {noData}, error: {error}")


def main():
    #get trias data
    queryStationList = [
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

    allLiveJourneysDict = {
        "info": {
            "calculationTimeMs":          0,
            "responseTimestamp":          None,
            "attachedDataFormatRevision": "2026.02.26",
            "license":                    "DL-DE/BY-2-0",
            "rawDataSourceUrl":           "https://mobidata-bw.de/dataset/trias",
        },
        "journeys": dict(),
    }
    for stationTuple in queryStationList:
        stopEventResponse        = triasApi.getStopEvents(stationName, stationRef, numResults=100)
        timestampStr, calcTimeMs = triasApi.getResponseStatistics(stopEventResponse)
        currentTime              = datetime.now().astimezone()
        allLiveJourneysDict["info"]["responseTimestamp"] = timestampStr
        allLiveJourneysDict["info"]["calculationTimeMs"] += calcTimeMs
        serviceDelivery = stopEventResponse["Trias"]["ServiceDelivery"]

        for stopEvent in serviceDelivery["DeliveryPayload"]["StopEventResponse"]
            try:
                journey     = Journey(stopEvent)
                liveJourney = LiveJourney(journey, evaluationTime)
                allLiveJourneysDict["journeys"] |= liveJourney.as_dict()
            except Exception as e:
                logging.warning("no or invalid live data")

    #write live data into json
    with open(base_dir/"www/currentRunningTrains.json", "w") as outputfile:
        outputfile.write(json.dumps(allLiveJourneysDict, indent=4))

    #render livemap
    www_dir = base_dir/'www'
    try:
        from visualize_liveMap import render_liveMap
        render_liveMap(www_dir/"currentRunningTrains.json", base_dir/"svg_source"/"live_map_source_light.svg", www_dir/"live_map.svg")
    except Exception as e:
        logging.exception("Failed to update live map")

    #upload
    crawl_helperFunc.copy_www_to_webhost(www_dir)

if __name__ == "__main__":
    try:
        main()
    except Exception:
        logging.error("Unhandled exception:\n%s", traceback.format_exc())
        raise
