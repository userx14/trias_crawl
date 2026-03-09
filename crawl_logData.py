from datetime import datetime, timezone, timedelta
import xmltodict
from pathlib import Path
import logging
import sqlite3
import subprocess
import traceback

import triasApi

base_dir      = Path(__file__).parent
triasApi.requestorKey = open(base_dir/"requestor.key").read()
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s'
)

"""
logging.basicConfig(
    filename=base_dir/"error.log",
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s'
)
"""
def delaySeconds_from_serviceCall(serviceCallDict):
    if serviceCallDict is None:
        return None
    timetableTime = datetimeFromTriasDatetimeStr(serviceCallDict.get("TimetabledTime"))
    estimatedTime = datetimeFromTriasDatetimeStr(serviceCallDict.get("EstimatedTime"))
    if timetableTime is None or estimatedTime is None:
        return None
    return (estimatedTime - timetableTime).total_seconds()

def getIncidentText(serviceData):
    incidentText = None
    attributes = serviceData.get("Attribute")
    if attributes:
        #if there is only a single attribute, make it a list so the following code can correctely handle it
        attributes = attributes if isinstance(attributes, list) else [attributes]
        for att in attributes:
            if "Incident" in att["Code"]:
                if incidentText is not None:
                    logging.error(f'multiple incident messages {incidentText}, {att["Text"]["Text"]}')
                incidentText = att["Text"]["Text"]
    return incidentText

def logJourney(serviceData, allStops): #convert this journey into a compressed form for statistics db
    operatingDayRef = triasApi.datetimeFromTriasDateStr(serviceData["OperatingDayRef"])
    processedStopsList = []
    for stop in allStops:
        thisCall       = stop["CallAtStop"]
        ttbArr, estArr, ttbDep, estDep = triasApi.getArrAndDepTimes(thisCall)
        processedStopsList.append({
            "journeyRef":          serviceData["JourneyRef"],
            "operatingDay":        operatingDayRef.timestamp(),
            "stopIndex":           thisCall["StopSeqNumber"],
            "stopPointName":       thisCall["StopPointName"]["Text"],
            "stopPointRef":        thisCall["StopPointRef"],
            "notServiced":         (thisCall.get("NotServicedStop") == "true"),
            "departureTimetable":  ttbDep.timestamp() if ttbDep is not None else None,
            "departureEstimate":   estDep.timestamp() if estDep is not None else None,
            "arrivalTimetable":    ttbArr.timestamp() if ttbArr is not None else None,
            "arrivalEstimate":     estArr.timestamp() if estArr is not None else None,
        })
    return {
        "journeyRef":           serviceData["JourneyRef"],
        "operatingDay":         operatingDayRef.timestamp(),
        "trainLineName":        serviceData["ServiceSection"]["PublishedLineName"]["Text"],
        "trainDestination":     serviceData["DestinationText"]["Text"],
        "trainOrigin":          serviceData["OriginText"]["Text"],
        "trainIncidentMessage": triasApi.getIncidentText(serviceData),
        "isCancelled":          (serviceData.get("Cancelled") == "true"),
        "isUnplanned":          (serviceData.get("Unplanned") == "true"),
        "isDeviated":           (serviceData.get("Deviation") == "true"),
        "stopsList":            processedStopsList,
    }

def getSqlConnection():
    sqlJourneyTableInit = """
    CREATE TABLE IF NOT EXISTS journeys (
        operatingDay         INTEGER NOT NULL,      /*unix time utc*/
        journeyRef           TEXT,
        trainLineName        TEXT,
        trainOrigin          TEXT,
        trainDestination     TEXT,
        trainIncidentMessage TEXT,
        isCancelled          INTEGER,               /*boolean*/
        isUnplanned          INTEGER,               /*boolean*/
        isDeviated           INTEGER,               /*boolean*/
        PRIMARY KEY (operatingDay, journeyRef)
    );"""

    sqlStopTableInit = """CREATE TABLE IF NOT EXISTS stops (
        operatingDay        INTEGER NOT NULL,       /*unix time utc*/
        journeyRef          TEXT NOT NULL,
        stopIndex           INTEGER NOT NULL,
        stopPointName       TEXT,
        stopPointRef        TEXT,
        notServiced         INTEGER,                /*boolean*/
        departureTimetable  INTEGER,                /*unix time utc*/
        departureEstimate   INTEGER,                /*unix time utc*/
        arrivalTimetable    INTEGER,                /*unix time utc*/
        arrivalEstimate     INTEGER,                /*unix time utc*/
        PRIMARY KEY (operatingDay, journeyRef, stopIndex),
        FOREIGN KEY (operatingDay, journeyRef) REFERENCES journeys(operatingDay, journeyRef)
    );
    """
    yearInt = datetime.now().year
    connection = sqlite3.connect(base_dir/f'loggedJourney_{yearInt}.db')
    cursor = connection.cursor()
    cursor.execute(sqlJourneyTableInit)
    cursor.execute(sqlStopTableInit)
    connection.commit()
    cursor.close()
    return connection

def insertJourneysInDb(journeys):
    connection = getSqlConnection()
    cursor = connection.cursor()
    journey_keys = [
        "operatingDay", "journeyRef", "trainLineName", 
        "trainOrigin", "trainDestination", "trainIncidentMessage", 
        "isCancelled", "isUnplanned", "isDeviated",
    ]
    for journey in journeys:
        journey_data = tuple(journey[key] for key in journey_keys)
        insert_journey_data = f'''
            INSERT OR REPLACE INTO journeys ({', '.join(journey_keys)})
            VALUES ({', '.join(['?'] * len(journey_keys))});
        '''
        cursor.execute(insert_journey_data, journey_data)

        for stop in journey["stopsList"]:
            stop_keys = [
                "operatingDay", "journeyRef", "stopIndex",
                "stopPointName", "stopPointRef", "notServiced",
                "departureTimetable", "departureEstimate", "arrivalTimetable",
                "arrivalEstimate",
            ]
            stop_data = tuple(stop[key] for key in stop_keys)
            insert_stop_data = f'''
                INSERT OR REPLACE INTO stops ({', '.join(stop_keys)})
                VALUES ({', '.join(['?'] * len(stop_keys))});
            '''
            cursor.execute(insert_stop_data, stop_data)
    connection.commit()
    connection.close()

def copy_www_to_webhost(local_path, remote_path = 'bwp@p0ng.de:/var/www/html/trias/'):
    for src_path in local_path.iterdir():
        scp_command = ['/run/current-system/sw/bin/scp', src_path, remote_path]
        try:
            subprocess.run(scp_command, check=True)
        except subprocess.CalledProcessError as e:
            logging.error(f"Error during file copy: {e}")

def acquireTrainLineFilter(lineName):
    if "S" in lineName:
        return True
    return False

def logFinishedJourneys():
    currentTime = datetime.now().astimezone()

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

    allLoggedJourneys = []
    for stationTuple in checkAtStations:
        logging.info(f"station {stationTuple[0]}")
        stopEventResponse = triasApi.getStopEvents(*stationTuple, 100)
        serviceDelivery   = stopEventResponse["Trias"]["ServiceDelivery"]
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

                allStops          = triasApi.combineAndFixStops(stopEvent)
                if not triasApi.hasAnyRealtimeData(allStops):
                    continue

                extrapolatedStops = triasApi.extrapolateStopsWithClosestDelay(allStops)
                if extrapolatedStops is None:
                    continue

                #check if the journey has already started
                if currentTime < extrapolatedStops[0]["ttbDep"]:
                    continue

                #check if the journey has already ended
                if extrapolatedStops[-1]["estArr"] < currentTime:
                    continue

                allLoggedJourneys.append(logJourney(serviceData, allStops))
            except Exception as e:
                logging.error(traceback.format_exc())
    insertJourneysInDb(allLoggedJourneys)

def main():
    #get trias data
    logFinishedJourneys()

    www_dir = base_dir/'www'
    #render statmap for this week
    try:
        current_utc = datetime.now(timezone.utc)
        analysisEndDay = current_utc
        analysisStartDay = current_utc - timedelta(days=0)
        from visualize_statMap import update_stat_delay_map, update_stat_notServiced_map
        update_stat_delay_map(analysisStartDay, analysisEndDay, www_dir/"stat_map_delay_today.svg")
        update_stat_notServiced_map(analysisStartDay, analysisEndDay, www_dir/"stat_map_notServiced_today.svg")
    except Exception as e:
        logging.exception("Failed to update stat map for today")

    try:
        current_utc = datetime.now(timezone.utc)
        analysisEndDay = current_utc - timedelta(days=1)
        analysisStartDay = current_utc - timedelta(days=1)
        from visualize_statMap import update_stat_delay_map, update_stat_notServiced_map
        update_stat_delay_map(analysisStartDay, analysisEndDay, www_dir/"stat_map_delay_yesterday.svg")
        update_stat_notServiced_map(analysisStartDay, analysisEndDay, www_dir/"stat_map_notServiced_yesterday.svg")
    except Exception as e:
        logging.exception("Failed to update stat map for yesterday")

    try:
        current_utc = datetime.now(timezone.utc)
        analysisEndDay = current_utc
        analysisStartDay = current_utc - timedelta(days=7)
        from visualize_statMap import update_stat_delay_map, update_stat_notServiced_map
        update_stat_delay_map(analysisStartDay, analysisEndDay, www_dir/"stat_map_delay_week.svg")
        update_stat_notServiced_map(analysisStartDay, analysisEndDay, www_dir/"stat_map_notServiced_week.svg")
    except Exception as e:
        logging.exception("Failed to update stat map")

    #upload
    try:
        copy_www_to_webhost(www_dir)
    except Exception as e:
        logging.exception("Failed to upload to server")


if __name__ == "__main__":
    main()

