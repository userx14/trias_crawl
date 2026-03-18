from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, asdict
from pathlib import Path
from copy import deepcopy
import logging
import json
import subprocess
import traceback
import xmltodict
import sqlite3

base_dir = Path(__file__).parent
logging.basicConfig(
    #filename=base_dir/"error.log",
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s'
)

def sqlInitConnection():

    yearInt = datetime.now().year
    connection = sqlite3.connect(base_dir/f'loggedJourney_{yearInt}.db')
    cursor = connection.cursor()
    cursor.execute(sqlJourneyTableInit)
    cursor.execute(sqlStopTableInit)
    connection.commit()
    cursor.close()
    return connection

inputDb  = "loggedJourney_2026.db"
outputDb = "loggedJourney_2026_converted.db"

def main():

    sqlJourneyTableInit = """CREATE TABLE IF NOT EXISTS journeys (
        operatingDay INTEGER NOT NULL,      /*unix time utc*/
        journeyRef   TEXT,
        lineName     TEXT,
        origin       TEXT,
        destination  TEXT,
        incidentText TEXT,
        isCancelled  INTEGER,               /*boolean*/
        isUnplanned  INTEGER,               /*boolean*/
        isDeviated   INTEGER,               /*boolean*/
        PRIMARY KEY (operatingDay, journeyRef)
    );"""

    sqlStopTableInit = """CREATE TABLE IF NOT EXISTS stops (
        operatingDay        INTEGER NOT NULL,       /*unix time utc*/
        journeyRef          TEXT NOT NULL,
        stopIndex           INTEGER NOT NULL,
        stopPointName       TEXT,
        stopPointRef        TEXT,
        isNotServiced       INTEGER,                /*boolean*/
        departureTimetable  INTEGER,                /*unix time utc*/
        departureEstimate   INTEGER,                /*unix time utc*/
        arrivalTimetable    INTEGER,                /*unix time utc*/
        arrivalEstimate     INTEGER,                /*unix time utc*/
        PRIMARY KEY (operatingDay, journeyRef, stopIndex),
        FOREIGN KEY (operatingDay, journeyRef) REFERENCES journeys(operatingDay, journeyRef)
    );
    """

    connectionOut      = sqlite3.connect(outputDb)
    cursorOut          = connectionOut.cursor()
    cursorOut.execute(sqlJourneyTableInit)
    cursorOut.execute(sqlStopTableInit)

    connectionIn       = sqlite3.connect(inputDb)
    cursorIn           = connectionIn.cursor()

    #check if there are any stops without journey
    sqlStatem = """SELECT * FROM stops t2
       WHERE NOT EXISTS (
           SELECT 1
           FROM journeys t1
           WHERE t1.journeyRef = t2.journeyRef
    );"""
    cursorIn.execute(sqlStatem)
    nonMatchingStops    = cursorIn.fetchall()
    print(nonMatchingStops)


    cursorIn.execute(f"SELECT * FROM journeys;")
    journeys    = cursorIn.fetchall()
    keysJourney = list(map(lambda x: x[0], cursorIn.description))
    for journeyData in journeys:
        journeyDict = dict()
        for keyIdx, key in enumerate(keysJourney):
            journeyDict[key] = journeyData[keyIdx]
        journeyRef      = journeyDict["journeyRef"]
        operatingDay    = journeyDict["operatingDay"]
        journeyDict["lineName"] = journeyDict.pop("trainLineName")
        journeyDict["origin"] = journeyDict.pop("trainOrigin")
        journeyDict["destination"] = journeyDict.pop("trainDestination")
        journeyDict["incidentText"] = journeyDict.pop("trainIncidentMessage")


        for journeyKey, journeyValue in journeyDict.items():
            if isinstance(journeyValue, datetime):
                journeyDict[journeyKey] = journeyValue.timestamp()
        sqlJourneyData     = tuple(journeyDict.values())
        sqlJourneyCommand  = f'''
            INSERT OR REPLACE INTO journeys ({', '.join(journeyDict.keys())})
            VALUES ({', '.join(['?'] * len(journeyDict))});
        '''
        cursorOut.execute(sqlJourneyCommand, sqlJourneyData)


        #get all stops
        cursorIn.execute(f"SELECT * FROM stops WHERE operatingDay=? AND journeyRef=? ORDER BY stopIndex ASC;", (operatingDay,journeyRef,))
        stops = cursorIn.fetchall()
        keysStop = list(map(lambda x: x[0], cursorIn.description))
        duplicateStopOffset = 0
        for stopData in stops:
            thisStopDict = dict()
            for keyIdx, key in enumerate(keysStop):
                thisStopDict[key] = stopData[keyIdx]
            thisStopDict["isNotServiced"] = thisStopDict.pop("notServiced")
            thisStopDict["stopIndex"]    += duplicateStopOffset
            idx = stops.index(stopData)
            if idx!=len(stops)-1:
                nextStopDict = dict()
                for keyIdx, key in enumerate(keysStop):
                    nextStopDict[key] = stops[idx+1][keyIdx]
                if thisStopDict["stopPointRef"] == nextStopDict["stopPointRef"]:
                    duplicateStopOffset -= 1
                    continue
            sqlStopData    = tuple(thisStopDict.values())
            sqlStopCommand = f'''
                INSERT OR REPLACE INTO stops ({', '.join(thisStopDict.keys())})
                VALUES ({', '.join(['?'] * len(thisStopDict))});
            '''
            cursorOut.execute(sqlStopCommand, sqlStopData)

    connectionOut.commit()
    connectionOut.close()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        logging.error("Unhandled exception:\n%s", traceback.format_exc())
        raise
