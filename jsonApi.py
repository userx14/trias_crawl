import json
import requests
from pathlib import Path
import xmltodict


base_dir = Path(__file__).parent
url = open(base_dir/"jsonApi.key").read().replace("\n", "").replace("\r","")
requestHeader = {'User-Agent': 'Python-urllib/3.10'}


def stopFinderRequest(stopName, stopType="stop"):
    payload = {
        "name_sf": stopName,
        "type_sf": stopType,
    }
    response = requests.get(url+"XML_STOPFINDER_REQUEST", params = payload, headers=requestHeader)
    return xmltodict.parse(response.content)

def servingLinesRequest():
    requests.get(url+"XML_SERVINGLINES_REQUEST")
    pass

def dmRequest(stopName):
    payload = {
        "nameInfo_dm": stopName,
        "language": "de",
        "typeInfo_dm": "stopID",
        "useRealtime": 1,
    }
    response = requests.get(url+"XML_DM_REQUEST", params = payload, headers=requestHeader)
    return xmltodict.parse(response.content)


def addInfoRequest():
    payload = {
        "operatorCode": "DB",
        "filterDateValid": datetime.today().strftime('%d-%m-%Y'),
    }
    requests.get(url+"XML_ADDINFO_REQUEST", params = payload, headers=requestHeader)
    pass

jsonPayload = stopFinderRequest("Backnang", stopType="any")
print(jsonPayload["itdRequest"]["itdStopFinderRequest"]["itdOdv"])
