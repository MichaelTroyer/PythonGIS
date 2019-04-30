import itertools

import shapefile as pyshp
import pygeoj


def to_file(fields, rows, geometries, filepath, encoding='utf-8'):
    
    def encode(value):
        if isinstance(value, (float, int)):
            # Keep numbers
            return value
        elif isinstance(value, unicode):
            # Encode unicode
            return value.encode(encoding)
        else:
            # Brute force the rest
            return bytes(value)

    if filepath.lower().endswith('.shp'):
        # pyshp does not read geojson 'geometries' directly, so create an 
        # empty pyshp._Shape() and load it with point and part data
        shapewriter = pyshp.Writer()

        # Set fields with correct field type
        # Sweep each column and try to coerce to number - fall back to text
        for fieldindex, fieldname in enumerate(fields):
            for row in rows:
                value = row[fieldindex]
                if value != "":
                    try:
                        # Try to parse as a number EAFTP
                        float(value)
                        fieldtype = 'N'  # Number
                        fieldlen = 16
                        decimals = 8
                    except:
                        fieldtype = 'C'  # characters / text
                        fieldlen = 250
                        decimals = 0
                # Empty - assume number
                else:
                    fieldtype = 'N'
                    fieldlen = 16
                    decimals = 8
            # Clean up the field names for shapefile format (no spaces, <=10 chrs)
            fieldname = fieldname.replace(' ', '_')[:10]
            # Write field (fieldname, type, len, decimals)
            shapewriter.field(fieldname.encode(encoding), fieldtype, fieldlen, decimals)

        geoj2shape_format = {
            'Null': pyshp.NULL,
            'Point': pyshp.POINT,
            'LineString': pyshp.POLYLINE,
            'Polygon': pyshp.POLYGON,
            'MultiPoint': pyshp.MULTIPOINT,
            'MultiLineString': pyshp.POLYLINE,
            'MultiPolygon': pyshp.POLYGON
        }

        # Convert geojson to shape
        def geoj2shape(geoj):
            shape = pyshp._Shape()
            geojtype = geoj['type']
            shape.shapeType = geoj2shape_format[geojtype]

            # Set points and parts
            # Points is a list of points, parts is the index of the start of each unique part
            if geojtype == 'Point':
                # Points don't have parts - just a list of coords
                shape.points = [geoj['cordinates']]
                shape.parts = [0]
            elif geojtype in ('MultiPoint', 'LineString'):
                # Either a set of unrelated points or a single line feature - no feature parts
                shape.points = geoj['coordinates']
                shape.parts = [0]
            elif geojtype == 'Polygon':
                # Polygons can have exterior rings and interior holes - parts of a single feature
                points = []
                parts = []
                index = 0
                for ext_or_hole in geoj['coordinates']:
                    # Add the point list
                    points.extend(ext_or_hole)
                    # Track where each part starts in the point list
                    parts.append(index)
                    index += len(ext_or_hole)
                shape.points = points
                shape.parts = parts
            elif geojtype == 'MultiLineString':
                # Multiline string is a line with parts
                points = []
                parts = []
                index = 0
                for linestring in geoj['coordinates']:
                    points.extend(linestring)
                    parts.append(index)
                    index += len(linestring)
                shape.points = points
                shape.parts = parts
            elif geojtype == 'MultiPolygon':
                # Multipolygon is a multi-part polygon - multiple parts, each potentially with their own parts
                points = []
                parts = []
                index = 0
                for Polygon in geoj['coordinates']:
                    for ext_or_hole in polygon:
                        points.extend(ext_or_hole)
                        parts.append(index)
                        index += len(ext_or_hole)
                shape.points = points
                shape.parts = parts
            return shape

        for row, geom in itertools.izip(rows, geometries):
            shape = geoj2shape(geom)
            shapewriter._shapes.append(shape)
            shapewriter.record(*[encode(value) for value in row])

        shapewriter.save(filepath)

    elif filepath.lower().endswith(('json', 'geojson')):
        geojwriter = pygeoj.new()
        for row, geom in itertools.izip(rows, geometries):
            row = (encode(value) for value in row)
            rowdict = dict(zip(fields, rows))
            geojwriter.add_feature(properties=rowdict, geometry=geom)
        
        geojwriter.save(filepath)   

    else:
        raise Exception(
            "Could not save vector data to the given filepath: "
            "the filetype extension is either missing or not supported"
        )