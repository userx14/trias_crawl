from pydantic_xml import BaseXmlModel, element, attr
from typing import Union, Optional, List
from pydantic import field_validator, field_serializer
from datetime import datetime, timezone
import requests

sharedArgs = {
    "nsmap": {
        "": "http://www.vdv.de/trias",
        "siri": "http://www.siri.org.uk/siri",
        "xsi": "http://www.w3.org/2001/XMLSchema-instance"
    },
    "search_mode": "unordered",
}

class LocationName(BaseXmlModel, tag="LocationName", **sharedArgs):
    text: str = element(tag='Text')

class LocationRef(BaseXmlModel, tag="LocationRef", **sharedArgs):
    stop_point_ref: str = element(tag='StopPointRef')
    location_name: LocationName = element()

class Origin(BaseXmlModel, tag="Origin", **sharedArgs):
    dep_arr_time: Optional[datetime] = element(tag="DepArrTime", default=None)
    location_ref: LocationRef = element()
    @field_validator("dep_arr_time", mode="before")
    def ensure_utc(cls, value):
        if isinstance(value, str):
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return dt.astimezone(timezone.utc).replace(microsecond=0)
        if isinstance(value, datetime):
            return value.astimezone(timezone.utc).replace(microsecond=0)
        return None

class Destination(BaseXmlModel, tag="Destination", **sharedArgs):
    location_ref: LocationRef = element()

class TripRequestParams(BaseXmlModel, tag="Params", **sharedArgs):
    number_of_results:           int = element(tag='NumberOfResults')
    include_track_sections:     bool = element(tag='IncludeTrackSections')
    include_intermediate_stops: bool = element(tag='IncludeIntermediateStops')
    include_leg_projection:     bool = element(tag='IncludeLegProjection')
    include_fares:              bool = element(tag='IncludeFares')

class TripRequest(BaseXmlModel, tag="TripRequest", **sharedArgs):
    origin:            Origin = element()
    destination:  Destination = element()
    params: TripRequestParams = element()

"""
class Restrictions(BaseXmlModel, tag='Restrictions', **sharedArgs):
    type:             Optional[str] = element(tag="Type",            default=None)
    language:         Optional[str] = element(tag="Language",        default=None)
    numberOfResults:  Optional[int] = element(tag="NumberOfResults", default=None)
    includePtModes:  Optional[bool] = element(tag="IncludePtModes",  default=None)
"""
class TripInfoRequestParams(BaseXmlModel, tag="Params", **sharedArgs):
    include_intermediate_stops: bool = element(tag="IncludeIntermediateStops")
    include_track_sections: bool     = element(tag="IncludeTrackSections")
    include_position: bool           = element(tag="IncludePosition")

class GeoPosition(BaseXmlModel, tag="GeoPosition", **sharedArgs):
    longitude:          float = element(tag="Longitude")
    latitude:           float = element(tag="Latitude")
    altitude: Optional[float] = element(tag="Altitude", default=None)

class GeoRestriction(BaseXmlModel, tag="GeoRestriction", **sharedArgs):
    pass

class InitialLocationInputStructure(BaseXmlModel, tag="InitialInput", **sharedArgs):
    location_name:   str                      = element(tag="LocationName")
    geo_position:    Optional[GeoPosition]    = element(default=None)
    geo_restriction: Optional[GeoRestriction] = element(default=None)
    
class PtModeFilterStructure(BaseXmlModel, tag="PtModes", **sharedArgs):
    exclude: bool = element(tag="Exclude")
    pt_mode: str  = element(tag="PtMode")

class LocationParamStructure(BaseXmlModel, tag="Restrictions", **sharedArgs):
    type:                       Optional[str] = element(tag="Type",                  default=None)
    usage:                      Optional[str] = element(tag="Usage",                 default=None)
    pt_modes: Optional[PtModeFilterStructure] = element(                             default=None)
    operator_filter:            Optional[str] = element(tag="OperatorFilter",        default=None)
    locality_ref:         Optional[List[int]] = element(tag="LocalityCode",          default=None)
    point_of_interest_filter:   Optional[str] = element(tag="PointOfInterestFilter", default=None)
    number_of_results:          Optional[int] = element(tag="NumberOfResults",       default=None)
    continue_at:                Optional[int] = element(tag="ContinueAt",            default=None)
    include_pt_modes:          Optional[bool] = element(tag="IncludePtModes",        default=None)

class LocationInformationRequest(BaseXmlModel, tag="LocationInformationRequest", **sharedArgs):
    initial_input:     InitialLocationInputStructure = element()
    location_param_structure: LocationParamStructure = element()

class InternationalText(BaseXmlModel, **sharedArgs):
    text:               str = element(tag="Text")
    language: Optional[str] = element(tag="Language", default=None)

class StopPoint(BaseXmlModel, tag="StopPoint", **sharedArgs):
    stop_point_ref:                str = element(tag="StopPointRef")
    stop_point_name: InternationalText = element(tag="StopPointName")
    locality_ref:        Optional[str] = element(tag="LocalityRef", default=None)

class StopPlace(BaseXmlModel, tag="StopPlace", **sharedArgs):
    stop_place_ref:                      str = element(tag="StopPlaceRef")
    stop_place_name:       InternationalText = element(tag="StopPlaceName")
    name_suffix: Optional[InternationalText] = element(tag="NameSuffix",  default=None)
    locality_ref:              Optional[str] = element(tag="LocalityRef", default=None)  

class LocationStructureStopPoint(BaseXmlModel, **sharedArgs):
    stop_point:                  StopPoint = element()
    location_name: List[InternationalText] = element(tag="LocationName")
    geo_position:              GeoPosition = element()

class LocationStructureStopPlace(BaseXmlModel, **sharedArgs):
    stop_place:                  StopPlace = element()
    location_name: List[InternationalText] = element(tag="LocationName")
    geo_position:              GeoPosition = element()
    
class LocationResultStructure(BaseXmlModel, tag="LocationResult", **sharedArgs):
    location: Union[LocationStructureStopPoint, LocationStructureStopPlace] = element(tag="Location")
    complete:                              bool = element(tag="Complete")
    probability:                Optional[float] = element(tag="Probability", default=None)
    mode:                         Optional[str] = element(tag="Mode")

class LocationInformationResponse(BaseXmlModel, tag="LocationInformationResponse", **sharedArgs):
    location_results_list: List[LocationResultStructure] = element()

class TripInfoRequest(BaseXmlModel, tag="TripInfoRequest", **sharedArgs):
    journey_ref: str                = element(tag="JourneyRef")
    operating_day_ref: datetime     = element(tag="OperatingDayRef")
    params: TripInfoRequestParams   = element()
    @field_validator('operating_day_ref', mode='before')
    def ensure_utc(cls, value):
        if isinstance(value, str):
            dt = datetime.strptime(value, "%Y-%m-%dT")
            return dt.replace(tzinfo=timezone.utc)
        if isinstance(value, datetime):
            return value.astimezone(timezone.utc)
        return None
        
    @field_serializer("operating_day_ref")
    def serialize_date_only(self, value: datetime):
        return value.date().isoformat() + "T"

class RequestPayload(BaseXmlModel, tag="RequestPayload", **sharedArgs):
    location_information_request: Optional[LocationInformationRequest] = element(
        tag="LocationInformationRequest",
        default=None
    )
    trip_info_request: Optional[TripInfoRequest] = element(
        tag="TripInfoRequest",
        default=None
    )

class ServiceRequest(BaseXmlModel, tag="ServiceRequest", **sharedArgs):
    request_timestamp: datetime     = element(tag="RequestTimestamp",  ns="siri")
    requestor_ref: str              = element(tag='RequestorRef',      ns="siri")
    message_identifier: str         = element(tag="MessageIdentifier", ns="siri")
    request_payload: RequestPayload = element(tag="RequestPayload")
    @field_validator("request_timestamp", mode="before")
    def ensure_utc(cls, value):
        if isinstance(value, str):
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return dt.astimezone(timezone.utc).replace(microsecond=0)
        if isinstance(value, datetime):
            return value.astimezone(timezone.utc).replace(microsecond=0)
        return None  
    @field_serializer("request_timestamp")
    def serialize_date_only(self, value: datetime):
        return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

class DeliveryPayload(BaseXmlModel, tag="DeliveryPayload", **sharedArgs):
    pass

class ServiceDelivery(BaseXmlModel, tag="ServiceDelivery", **sharedArgs):
    response_timestamp: datetime      = element(tag="ResponseTimestamp",  ns="siri")
    producer_ref: str                 = element(tag="ProducerRef",        ns="siri")
    status: str                       = element(tag="Status",             ns="siri")
    language: str                     = element(tag="Language",           ns="siri")
    calc_time: int                    = element(tag="CalcTime")
    delivery_payload: DeliveryPayload = element()

class Trias(BaseXmlModel, tag="Trias", **sharedArgs):
    version: str = attr()
    service_request:   Optional[ServiceRequest] = element(default=None)
    service_delivery: Optional[ServiceDelivery] = element(default=None)
    def query(self, url):
        xmlTx = self.to_xml(skip_empty=True)
        requestHeader = {"Content-Type": "application/xml; charset=utf-8", "User-Agent": "Python-urllib/3.10"}
        response = requests.post(url, data=xmlTx, headers=requestHeader)
        return response.content
    

"""
with open("LocationInformationRequest_findTrainStations.xml", "rb") as f:
    xml_content = f.read()

trias_obj = Trias.from_xml(xml_content)
print(trias_obj)

from xml.dom import minidom
from pathlib import Path
rough_xml = trias_obj.to_xml()
parsed = minidom.parseString(rough_xml)
pretty_xml = parsed.toprettyxml(indent="    ", encoding="utf-8")
output_file = Path("TripInformationRequest_out.txt")
output_file.write_bytes(pretty_xml)
"""