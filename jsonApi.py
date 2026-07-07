import json
import requests
from pathlib import Path
import xmltodict
from datetime import datetime, UTC

base_dir = Path(__file__).parent
url = open(base_dir/"jsonApi.key").read().replace("\n", "").replace("\r","")
requestHeader = {'User-Agent': 'Python-urllib/3.10'}

"""
def tripStopTimesRequest(linename, stop):
    payload = {
        "hideBannerInfo": 1,
        "line": "sbg:07216: :R:j23",
        "stopID": "6900590",
        "itdDateDay":    "23",
        "itdDateMonth":  "11",
        "itdDateYear":   "2023",
        "itdTimeHour":   "07",
        "itdTimeMinute": "15",
        "tripCode": "36",
        "useRealtime": 1,
    }
    response = requests.get(url+"XML_TRIPSTOPTIMES_REQUEST", params = payload, headers=requestHeader)
    print(response.content)
    print(response)
    #return xmltodict.parse(response.content)["itdRequest"]["itdStopFinderRequest"]["itdOdv"]



def stopFinderRequest(stopName):
    payload = {
        "hideBannerInfo": 1,
        "name_sf": stopName,
        "type_sf": "any",
        "useLocalityMainStop": 1,
        "anyObjFilter_sf": 2 #only stops
    }
    response = requests.get(url+"XML_STOPFINDER_REQUEST", params = payload, headers=requestHeader)
    return xmltodict.parse(response.content)["itdRequest"]["itdStopFinderRequest"]["itdOdv"]
    #maybe add? ["itdOdvName"]["odvNameElem"]

def servingLinesRequest(stopName):
    payload = {
        "hideBannerInfo": 1,
        "commonMacro": "servinglines",
        "mode": "odv",
        "name_sl": stopName,
        "type_sl": "any",
        #"lsShowTrainsExplicit": 1,
        #"lineReqType": 0 #maybe limit this
    }
    response = requests.get(url+"XML_SERVINGLINES_REQUEST", params = payload, headers=requestHeader)
    return xmltodict.parse(response.content)#["itdRequest"]

def dmRequest(stopId):
    payload = {
        "hideBannerInfo": 1,
        "mode": "direct",
        "name_dm": stopId,
        "type_dm": "any",
        "itdDateDay": datetime.now().strftime('%d'),
        "itdDateMonth": datetime.now().strftime('%m'),
        "itdDateYear": datetime.now().strftime('%Y'),
        "itdTimeHour": datetime.now().strftime('%H'),
        "itdTimeMinute": datetime.now().strftime('%M'),
        "language": "de",
        "limit": 10, #how many results maximum
        "useRealtime": 1,
        "includedMeans": 1, # search exclusively
        "inclMOT_1": 1,     # for S-Bahn (Ubahn would be (2, 3, 4), Train (0))
    }
    response = requests.get(url+"XML_DM_REQUEST", params = payload, headers=requestHeader)
    print(response.content)
    return xmltodict.parse(response.content)["itdRequest"]["itdDepartureMonitorRequest"]
"""

def addInfoRequest():
    """
    payload = {
        "hideBannerInfo": 1,
        "operatorCode": "DB",
        #"filterDateValid": datetime.now(UTC).strftime('%d-%m-%Y'),
        "filterMOTType": 1,
        "filterProviderCode": "VVS",
        #"filterProviderCode": "RIS", #only disruptions
    }"""
    payload = {
        "hideBannerInfo": 1,
        #"operatorCode": "DB",
        "filterDateValid": datetime.now(UTC).strftime('%d-%m-%Y'),
        "filterMOTType": 1,
        #"filterProviderCode": "VVS",
        #"filterProviderCode": "RIS", #only disruptions
    }
    response = requests.get(url+"XML_ADDINFO_REQUEST", params = payload, headers=requestHeader)
    return xmltodict.parse(response.content)["itdRequest"]["itdAddInfoRequest"]


"""
jsonPayload = stopFinderRequest("Backnang, Bahnhof")
print(jsonPayload.keys())
for element in jsonPayload["itdOdvName"]["odvNameElem"]:
    print(f"{element}\n")
"""

"""
print("not working yet, seems to output nothing, why?")
jsonPayload = servingLinesRequest("de:08119:7600")
print(jsonPayload)
servingLines = jsonPayload["itdTTBRequest"]["itdServingLines"]["itdServingLine"]
for line in servingLines:
    print(f"{line}\n")


"""
def itdDatetimeToPython(dictIn):
    return datetime.strptime(f"{dictIn['itdDate']['@day']}.{dictIn['itdDate']['@month']}.{dictIn['itdDate']['@year']} {dictIn['itdTime']['@hour']}:{dictIn['itdTime']['@minute']}", "%d.%m.%Y %H:%M").replace(tzinfo=UTC).astimezone()
def ensure_list(x):
    if isinstance(x, list):
        return x
    return [x]
"""
jsonPayload = dmRequest("de:08119:7600")
for servingLine in jsonPayload["itdServingLines"]["itdServingLine"]:
    print(f"symbol {servingLine['@symbol']}, line {servingLine['motDivaParams']['@line']}")
    #print(f"srvLine {servingLine}")
    print("\n")
print(jsonPayload)
for departure in jsonPayload["itdDepartureList"]["itdDeparture"]:
    print(f"{departure}")
    print(itdDatetimeToPython(departure["itdDateTime"]))
    if "itdRTDateTime" in departure.keys():
        print(itdDatetimeToPython(departure["itdRTDateTime"]))
    print("\n")
"""
jsonPayload = addInfoRequest()
allTravelInfoDict = {
        "info": {
            "calculationTimeMs":          0,
            "responseTimestamp":          None,
            "attachedDataFormatRevision": "2026.06.11",
            "license":                    "DL-DE/BY-2-0",
            "rawDataSourceUrl":           "https://mobidata-bw.de/dataset/",
        },
        "disruptions": [],
    }
#print(jsonPayload)
if jsonPayload["itdAdditionalTravelInformations"] is None:
    print("no data")
    exit(0)
for travelInfo in ensure_list(jsonPayload["itdAdditionalTravelInformations"]["itdAdditionalTravelInformation"]):
    try:
        resultDict = {}
        concernedLines = []
        for line in ensure_list(travelInfo["concernedLines"]["line"]):
            concernedLines.append(line["@number"]+line["@supplement"])
        resultDict["concernedLines"]                     = sorted(list(set(concernedLines)))
        resultDict["shortText"]                          = travelInfo["infoLink"]["infoLinkText"]
        resultDict["fullText"]                           = travelInfo["infoLink"]["infoText"]["content"]
        concernedStops = []
        if travelInfo["concernedStops"]:
            for stop in ensure_list(travelInfo["concernedStops"]["stop"]):
                print(stop)
                #concernedStops.append({stop["@globalID"]: stop["@name"]})
            resultDict["concernedStops"]                     = concernedStops
        else:
            resultDict["concernedStops"]                     = None
        resultDict["priority"]                           = travelInfo["@priority"]
        resultDict["isValid"]                            = (travelInfo["@valid"]=="1")
        resultDict["creationTime"]                       = itdDatetimeToPython(travelInfo["creationTime"       ]["itdDateTime"]).timestamp()
        travelInfo["expirationDateTime"]["itdDateTime"]  = itdDatetimeToPython(travelInfo["expirationDateTime" ]["itdDateTime"])
        resultDict["validityPeriodStart"]                = itdDatetimeToPython(travelInfo["validityPeriod"     ]["itdDateTime"][0]).timestamp()
        resultDict["validityPeriodEnd"]                  = itdDatetimeToPython(travelInfo["validityPeriod"     ]["itdDateTime"][1]).timestamp()
        resultDict["publicationDurationStart"]           = itdDatetimeToPython(travelInfo["publicationDuration"]["itdDateTime"][0]).timestamp()
        resultDict["publicationDurationEnd"]             = itdDatetimeToPython(travelInfo["publicationDuration"]["itdDateTime"][1]).timestamp()
        resultDict["providerCode"]                       = travelInfo["@providerCode"]
        allTravelInfoDict["disruptions"].append(resultDict)
    except Exception as e:
        print(f"Failed to parse travel info: {e}")
    """
    travelInfo["creationTime"]["itdDateTime"] = itdDatetimeToPython(travelInfo["creationTime"]["itdDateTime"])
    travelInfo["expirationDateTime"]["itdDateTime"] = itdDatetimeToPython(travelInfo["expirationDateTime"]["itdDateTime"])
    for i in range(2):
        travelInfo["publicationDuration"]["itdDateTime"][i] = itdDatetimeToPython(travelInfo["publicationDuration"]["itdDateTime"][i])
        travelInfo["validityPeriod"]["itdDateTime"][i] = itdDatetimeToPython(travelInfo["validityPeriod"]["itdDateTime"][i])
    """
    """
    for attributeKey, attributeValue in travelInfo.items():
        print(f"{attributeKey}:\n{attributeValue}\n\n")
    """


    #print(travelInfo["infoLink"]["infoLinkText"])

    """
    print("info text")
    print(travelInfo["infoLink"]["infoText"])
    print("\n")

    print("affected lines")
    print(travelInfo["concernedLines"]['line'])
    print("\n")
    #print(travelInfo["concernedStops"])
    """
#print(tripStopTimesRequest("ddb:92T03::H:j26", "de:08119:7600"))
#write live data into json
allTravelInfoDict["disruptions"].sort(
    key=lambda disruption: disruption.get("isValid", False),
    reverse=True
)
with open(base_dir/"www/travelInformation.json", "w") as outputfile:
    outputfile.write(json.dumps(allTravelInfoDict, indent=4))


