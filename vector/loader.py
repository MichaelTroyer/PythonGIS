import os

import shapefile as pyshp
import pygeoj


def from_file(filepath, encoding="utf8"):

    def decode(value):
        if isinstance(value, str): 
            return value.decode(encoding)
        else:
            return value
    
    # shapefile
    if filepath.lower().endswith(".shp"):
        shapereader = pyshp.Reader(filepath)
        
        # load fields, rows, and geometries
        # Field name is first value in field, first value in shapereader is delete flag
        fields = [decode(field[0]) for field in shapereader.fields[1:]]
        rows = [ [decode(value) for value in record] for record in shapereader.iterRecords()]
        def getgeoj(obj):
            """ Get list of geojson features and capture bbox if alreaday calculated"""
            # .__Geo_interface__ returns geojson dict
            geoj = obj.__geo_interface__
            # Shapefiles store feature bounding boxes - except points obvy
            if hasattr(obj, "bbox"):
                geoj["bbox"] = obj.bbox
            return geoj
        geometries = [getgeoj(shape) for shape in shapereader.iterShapes()]
        
        # load projection string from .prj file if exists
        if os.path.lexists(filepath[:-4] + ".prj"):
            crs = open(filepath[:-4] + ".prj", "r").read()
        else: crs = "+proj=longlat +ellps=WGS84 +datum=WGS84 +no_defs"
        
        return fields, rows, geometries, crs

    # geojson file
    elif filepath.lower().endswith((".geojson",".json")):
        geojfile = pygeoj.load(filepath)

        # load fields, rows, and geometries
        fields = [decode(field) for field in geojfile.common_attributes]
        rows = [[decode(feat.properties[field]) for field in fields] for feat in geojfile]
        geometries = [feat.geometry.__geo_interface__ for feat in geojfile]

        # load crs
        crs = geojfile.crs
        
        return fields, rows, geometries, crs
    
    else:
        raise Exception(
            "Could not create vector data from the given filepath:"
            " the filetype extension is either missing or not supported"
            )






