import datetime
import itertools
import operator
import os
import sys

from collections import OrderedDict

import shapely
from shapely.geometry import asShape as geojson2shapely

import rtree

from . import loader
from . import saver


class Feature:
    def __init__(self, data, row, geometry, id=None):
        # data is a reference to parent
        # geometry must be a geojson dictionary
        self._data = data
        self.row  = list(row)
        
        bbox = geometry.get("bbox", None)
        self._cached_bbox = bbox

        self.geometry = geometry.copy()

        # ensure it is same geometry type as parent
        geotype = self.geometry["type"]
        if self._data.type: 
            if "Point" in geotype and self._data.type == "Point": pass
            elif "LineString" in geotype and self._data.type == "LineString": pass
            elif "Polygon" in geotype and self._data.type == "Polygon": pass
            else:
                raise TypeError("Each feature geometry must be of the same type as the file it is attached to")
        else: self._data.type = geotype.replace("Multi", "")
        
        if id == None:
            id = next(self._data._id_generator)  #Use parents ID generator
        self.id = id

    def __getitem__(self, i):
        if isinstance(i, (str, unicode)):
            i = self._data.fields.index(i)
        return self.row[i]

    def __setitem__(self, i, setvalue):
        if isinstance(i, (str, unicode)):
            i = self._data.fields.index(i)
        self.row[i] = setvalue

    @property
    def bbox(self):        
        """bounding box is represented as (xmin, ymin, xmax ymax)"""
        if not self._cached_bbox:
            geotype = self.geometry["type"]
            coords = self.geometry["coordinates"]

            if geotype == "Point":
                x, y = coords
                bbox = [x, y, x, y]
            elif geotype in ("MultiPoint", "LineString"):
                xs, ys = itertools.izip(*coords)
                bbox = [min(xs), min(ys), max(xs), max(ys)]
            elif geotype == "MultiLineString":
                xs = [x for line in coords for x, y in line]
                ys = [y for line in coords for x, y in line]
                bbox = [min(xs), min(ys), max(xs), max(ys)]
            elif geotype == "Polygon":
                exterior = coords[0]
                xs, ys = itertools.izip(*exterior)
                bbox = [min(xs), min(ys), max(xs), max(ys)]
            elif geotype == "MultiPolygon":
                xs = [x for poly in coords for x, y in poly[0]]
                ys = [y for poly in coords for x, y in poly[0]]
                bbox = [min(xs), min(ys), max(xs), max(ys)]
            self._cached_bbox = bbox
        return self._cached_bbox

    def get_shapely(self):
        return geojson2shapely(self.geometry)

    def copy(self):
        geoj = self.geometry
        if self._cached_bbox:
            geoj["bbox"] = self._cached_bbox
        return Feature(self._data, self.row, geoj)


def ID_generator():
    i = 0
    while True:
        yield i
        i += 1


class VectorData:
    def __init__(self, filepath=None, feature_type=None, **kwargs):
        self.filepath = filepath

        # For enforcing feature types
        # if None, type enforcement will be based on first geometry found
        self.type = feature_type
        
        if filepath:
            fields, rows, geometries, crs = loader.from_file(filepath, **kwargs)
        else:
            fields, rows, geometries, crs = [], [], [], "+proj=longlat +ellps=WGS84 +datum=WGS84 +no_defs"

        self.fields = fields

        self._id_generator = ID_generator()
        
        # attach objectIDs
        ids_rows_geoms = itertools.izip(self._id_generator, rows, geometries)
        # Create the features
        featureobjs = (Feature(self, row, geom, id=id) for id, row, geom in ids_rows_geoms)
        # Store features in an OrderedDict keyed by objectID
        self.features = OrderedDict([
            (feat.id, feat) for feat in featureobjs
            ])
    
        self.crs = crs

    def __len__(self):
        return len(self.features)

    def __iter__(self):  # allows for feat in self
        for feat in self.features.itervalues():
            yield feat

    def __getitem__(self, i):  # allows self[featureID]
        if isinstance(i, slice):
            raise Exception("Can only get one feature at a time")
        else:
            return self.features[i]  # features is an OrderedDict

    def __setitem__(self, i, feature):
        """Will overwrite existing features"""
        if isinstance(i, slice):
            raise Exception("Can only set one feature at a time")
        else:
            self.features[i] = feature

    @property
    def bbox(self):
        """bounding box is represented as (xmin, ymin, xmax ymax)"""
        xmins, ymins, xmaxs, ymaxs = itertools.izip(*(feat.bbox for feat in self))
        xmin, xmax = min(xmins), max(xmaxs)
        ymin, ymax = min(ymins), max(ymaxs)
        bbox = (xmin, ymin, xmax, ymax)
        return bbox

    def add_feature(self, row, geometry):
        feature = Feature(self, row, geometry)
        self[feature.id] = feature

    def create_spatial_index(self):
        """Allows quick overlap search methods"""
        self.spindex = rtree.index.Index()
        for feat in self:
            self.spindex.insert(feat.id, feat.bbox)
    
    def quick_overlap(self, bbox):
        """
        Quickly get features whose bbox overlap the specified bbox via the spatial index.
        """
        if not hasattr(self, "spindex"):
            raise Exception("You need to create the spatial index before you can use this method")
        # ensure min, min, max, max pattern (why not enforce xmin, ymin, xmax, ymax ?)
        xs = bbox[0], bbox[2]
        ys = bbox[1], bbox[3]
        bbox = [min(xs), min(ys), max(xs), max(ys)]
        # return generator over results
        results = self.spindex.intersection(bbox)
        return (self[id] for id in results)

    def quick_nearest(self, bbox, n=1):
        """
        Quickly get n features whose bbox are nearest the specified bbox via the spatial index.
        """
        if not hasattr(self, "spindex"):
            raise Exception("You need to create the spatial index before you can use this method")
        # ensure min, min, max, max pattern (why not enforce xmin, ymin, xmax, ymax ?)
        xs = bbox[0],bbox[2]
        ys = bbox[1],bbox[3]
        bbox = [min(xs),min(ys),max(xs),max(ys)]
        # return generator over results
        results = self.spindex.nearest(bbox, num_results=n)
        return (self[id] for id in results)

    def save(self, savepath, **kwargs):
        fields = self.fields
        rowgeoms = ((feat.row, feat.geometry) for feat in self) 
        rows, geometries = itertools.izip(*rowgeoms)
        saver.to_file(fields, rows, geometries, savepath, **kwargs)

    def copy(self):
        new = VectorData()
        new.fields = [field for field in self.fields]
        # Point Feature copies to new parent - new
        featureobjs = (Feature(new, feat.row, feat.geometry) for feat in self)
        # Manually populate new.features since __init__ didn't from above
        new.features = OrderedDict([
            (feat.id, feat) for feat in featureobjs
            ])
        # only add to new if we have one already, else let new calc when needed
        if hasattr(self, "spindex"):
            new.spindex = self.spindex.copy()
        return new
