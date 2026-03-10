from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, asdict
from pathlib import Path
from copy import deepcopy
import logging
import json
import subprocess
import traceback
import xmltodict
import datetime
import triasApi
import crawl_helperFunc

@dataclass
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
        self.stopPointRef = stopCall["StopPointRef"]
        self.stopIndex = int(stopCall["StopSeqNumber"]) + stopIndexOffset

        arrival = stopCall.get("ServiceArrival")
        if arrival is not None:
            self.arrivalTimetable = triasApi.datetimeFromTriasDatetimeStr(arrival["TimetabledTime"])
            self.arrivalEstimate  = arrival.get("EstimatedTime")
            self.arrivalEstimate  = triasApi.datetimeFromTriasDatetimeStr(self.arrivalEstimate)
        else:
            self.arrivalTimetable = None
            self.arrivalEstimate  = None

        departure = stopCall.get("ServiceDeparture")
        if departure is not None:
            self.departureTimetable = triasApi.datetimeFromTriasDatetimeStr(departure["TimetabledTime"])
            self.departureEstimate  = departure.get("EstimatedTime")
            self.departureEstimate  = triasApi.datetimeFromTriasDatetimeStr(self.departureEstimate)
        else:
            self.departureTimetable = None
            self.departureEstimate  = None

        self.isNotServiced = (stopCall.get("NotServicedStop") == "true")


@dataclass
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
    stops:        list[Stop]

    def __init__(self, stopEvent):
        serviceData      = stopEvent["StopEvent"]["Service"]

        self.journeyRef   = serviceData["JourneyRef"]
        self.origin       = serviceData["OriginText"]["Text"]
        self.destination  = serviceData["DestinationText"]["Text"]
        self.operatingDay = serviceData["OperatingDayRef"]
        self.operatingDay = triasApi.datetimeFromTriasDateStr(self.operatingDay)
        self.stops        = []
        #process line name
        self.lineName = serviceData["ServiceSection"]["PublishedLineName"]["Text"]
        if not self.lineName.startswith("S"):
            raise ValueError(f"Not an S-Bahn Line: {self.lineName}")


        #process incidentText
        self.incidentText = None
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

@dataclass
class LiveJourney:
    journeyRef:   str
    lineName:     str
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

    def _getExtrapolatedDelaysAtStop(self, stopsList: list[Stop], stopIdx: int):
        delayBefore = None
        for stopBeforeIdx in range(stopIdx-1, -1, -1):
            stopBefore = stopsList[stopBeforeIdx]
            departureES = stopBefore.departureEstimate
            if departureES:
                departureTT = stopBefore.departureTimetable
                delayBefore = departureES - departureTT
                break
            arrivalES = stopBefore.arrivalEstimate
            if arrivalES:
                arrivalTT = stopBefore.arrivalTimetable
                delayBefore = arrivalES - arrivalTT
                break
        delayAfter = None
        for stopAfterIdx in range(stopIdx+1, len(stopsList)):
            stopAfter = stopsList[stopAfterIdx]
            arrivalES = stopAfter.arrivalEstimate
            if arrivalES:
                arrivalTT = stopAfter.arrivalTimetable
                delayAfter = arrivalES - arrivalTT
                break
            departureES = stopAfter.departureEstimate
            if departureES:
                departureTT = stopAfter.departureTimetable
                delayAfter = departureES - departureTT
                break
        return delayBefore, delayAfter

    def _isIntermediateNotServicedStop(self, stopsList: list[Stop], stopIdx: int):
        servicedStopBeforeExists = False
        for stopBeforeIdx in range(stopIdx-1, -1, -1):
            if not stopsList[stopBeforeIdx].isNotServiced:
                servicedStopBeforeExists = True
        servicedStopAfterExists = False
        for stopAfterIdx in range(stopIdx+1, len(stopsList)):
            if not stopsList[stopAfterIdx].isNotServiced:
                servicedStopAfterExists = True
        return (servicedStopBeforeExists and servicedStopAfterExists)


    def __init__(self, journey: Journey, evaluationTime: datetime.datetime):
        journey = deepcopy(journey)

        self.journeyRef = journey.journeyRef
        self.lineName = journey.lineName
        self.origin = journey.origin
        self.destination = journey.destination
        self.incidentText = journey.incidentText
        self.progressNextStop = None
        #extrapolate realtime data
        for stopIdx, stop in enumerate(journey.stops):
            if stop.departureTimetable and not stop.departureEstimate:
                delayBefore, delayAfter = self._getExtrapolatedDelaysAtStop(journey.stops, stopIdx)
                if stop.arrivalEstimate is not None:
                    delayAtStop = stop.arrivalEstimate - stop.arrivalTimetable
                    stop.departureEstimate = stop.departureTimetable + delayAtStop
                elif delayBefore is not None:
                    stop.departureEstimate = stop.departureTimetable + delayBefore
                elif delayAfter is not None:
                    stop.departureEstimate = stop.departureTimetable + delayAfter
                else:
                    ValueError("Insufficient realtime data")
            if stop.arrivalTimetable and not stop.arrivalEstimate:
                delayBefore, delayAfter = self._getExtrapolatedDelaysAtStop(journey.stops, stopIdx)
                if delayBefore is not None:
                    stop.arrivalEstimate = stop.arrivalTimetable + delayBefore
                elif stop.departureEstimate is not None:
                    delayAtStop = stop.departureEstimate - stop.departureTimetable
                    stop.arrivalEstimate = stop.arrivalTimetable + delayAtStop
                elif delayAfter is not None:
                    stop.arrivalEstimate = stop.arrivalTimetable + delayAfter
                else:
                    ValueError("Insufficient realtime data")

        for currentStopIdx in range(len(journey.stops)-1, -1, -1): #exclude first and last stop
            currentStop = journey.stops[currentStopIdx]
            if (currentStopIdx != len(journey.stops)-1) and currentStop.departureEstimate <= evaluationTime:
                # train is just past this stop
                self.currentStopName  = currentStop.stopPointName
                self.currentStopRef   = currentStop.stopPointRef
                self.delayMinutes     = currentStop.departureEstimate - currentStop.departureTimetable
                break
            elif (currentStopIdx != 0) and (currentStop.arrivalEstimate <= evaluationTime):
                # train is waiting at this stop
                self.progressNextStop = 0.0
                self.currentStopName  = currentStop.stopPointName
                self.currentStopRef   = currentStop.stopPointRef
                self.delayMinutes     = currentStop.arrivalEstimate - currentStop.arrivalTimetable
                break
        else:
            raise ValueError("Train has not yet started")
        if currentStopIdx == len(journey.stops) - 1:
            raise ValueError("Train has already ended")

        self.delayMinutes = int(self.delayMinutes.total_seconds() / 60)
        self.isCancelled = False
        if currentStop.isNotServiced:
            #skipped stops do not count as cancelation of the train
            if not self._isIntermediateNotServicedStop(journey.stops, currentStopIdx):
                self.isCancelled = True

        #find next non skipped stop
        for nextStopIdx in range(currentStopIdx + 1, len(journey.stops)):
            nextStop = journey.stops[nextStopIdx]
            if not nextStop.isNotServiced:
                self.nextStopName = nextStop.stopPointName
                self.nextStopRef  = nextStop.stopPointRef
                break
        else:
            raise ValueError("Train has no remaining serviced stops")


        #calculate progress
        if self.progressNextStop is None:
            progressToNextStop = evaluationTime - journey.stops[currentStopIdx].departureEstimate
            timeBetweenStops   = journey.stops[nextStopIdx].arrivalEstimate - journey.stops[currentStopIdx].departureEstimate
            if timeBetweenStops != 0:
                progressToNextStop /= timeBetweenStops
            else:
                raise ValueError("No travel time between stops")
        print(self.as_dict())

    def as_dict(self):
        liveJourneyDict = asdict(self)
        journeyRef = liveJourneyDict.pop("journeyRef")
        return {journeyRef: liveJourneyDict}

base_dir = Path(__file__).parent
triasApi.requestorKey = open(base_dir/"requestor.key").read()
logging.basicConfig(
    #filename=base_dir/"error.log",
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s'
)

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
        stopEventResponse        = triasApi.getStopEvents(*stationTuple, numResults=100)
        timestampStr, calcTimeMs = triasApi.getResponseStatistics(stopEventResponse)
        currentTime              = datetime.datetime.now().astimezone()
        allLiveJourneysDict["info"]["responseTimestamp"] = timestampStr
        allLiveJourneysDict["info"]["calculationTimeMs"] += calcTimeMs
        serviceDelivery = stopEventResponse["Trias"]["ServiceDelivery"]
        for stopEvent in serviceDelivery["DeliveryPayload"]["StopEventResponse"]["StopEventResult"]:
            #print(serviceDelivery)
            try:
                journey     = Journey(stopEvent)
                liveJourney = LiveJourney(journey, evaluationTime=currentTime)
                print(liveJourney.as_dict())
                allLiveJourneysDict["journeys"] |= liveJourney.as_dict()
            except Exception as e:
                traceback.print_exc()
                #logging.warning(f"no or invalid live data {e}")

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
