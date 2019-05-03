import itertools
import operator
import os
import sys

import PIL.Image
import PIL.ImageMath


class Cell(object):
    def __init__(self, band, col, row):
        self.band = band
        self.row, self.col = row, col

        def __repr__(self):
            return "Cell(col={}, row={}, value={}".format(self.col, self.row, self.value)

        @property
        def value(self):
            return self.band.cells[self.col, self.row]


class Band(object):
    def __init__(self, img, cells):
        self.img = img
        self.cells = cells

    def __iter__(self):
        width, height = self.img.size
        for row in xrange(height):
            for col in xrange(width):
                yield Cell(self, row, col)

    def get(self, col, row):
        return Cell(self, col, row)

    def set(self, col, row, value):
        self.cells[col, row] = value

    def copy(self):
        img = self.img.copy()
        cells = img.load()
        return Band(img, cells)


class RasterData(object):
    def __init__(self, filepath=None, data=None, image=None, **kwargs):
        self.filepath = filepath

        if filepath:
            info, bands, crs = loader.from_file(filepath)
        elif data:
            info, bands, crs = loader.from_lists(data, **kwargs)
        elif image:
            info, bands, crs = loader.from_image(image, **kwargs)
        else:
            info, bands, crs = loader.new(**kwargs)
        
        self.bands = [Band(img, cells) for img, cells in bands]
        self.info = info
        self.crs = crs

        self.update_geotransform()
    
    def __iter__(self):
        for band in self.bands:
            yield band
        
    @property
    def width(self):
        return self.bands[0].img.size[0]

    @property
    def height(self):
        return self.bands[0].img.size[1]

    def copy(self):
        new = RasterData(height=self.height, width=self.width, **self.info)
        new.bands = [band.copy() for band in self.bands]
        new._cached_mask = self._cached_mask
        return new

    def cell_to_geo(self, column, row):
        [xscale, xskew, xoffset, yscale, yskew, yoffset] = self.transform_coeffs
        x, y = column, row
        x_coord = x*xscale + y*xskew + xoffset
        y_coord = x*yscale + y*yskew + yoffset
        return x_coord, y_coord

    def geo_to_cell(self, x, y, fraction=False):
        [xscale, xskew, xoffset, yscale, yskew, yoffset] = self.inv_transform_coeffs
        column = x*xscale + y*xskew + xoffset
        row = x*yskew + y*yscale + yoffset
        if not fraction:
            # round to nearest cell
            column, row = int(round(column)), int(round(row))
        return column, row

    @property
    def bbox(self):
        x_left_coord, y_top_coord = self.cell_to_geo(0, 0)
        x_right_coord, y_bottom_coord = self.cell_to_geo(self.width, self.height)
        return [x_left_coord, y_top_coord, x_right_coord, y_bottom_coord]

    def update_geotransform(self):
        info = self.info

        # Get the cooefs needed to convert from raster to geographic space
        if info.get('transform_coeffs', None):
            [xscale, xskew, xoffset, yscale, yskew, yoffset] = info['transform_coeffs']
        else:
            xcell, ycell = info['xy_cell']
            xgeo, ygeo = info['xy_geo']
            xoffset, yoffset = xgeo - xcell, ygeo - ycell
            xscale, yscale = info['cellwidth'], info['cellheight']
            xskew, yskew = 0, 0
        self.transform_coeffs = [xscale, xskew, xoffset, yscale, yskew, yoffset]

        # Get the cooefs needed to convert from geographic space to rater
        # Sean Gilles affine.py : https://github.com/sgillies/affine
        a, b, c, d, e, f =  self.transform_coeffs
        det = a*e - b*d
        if det != 0:
            idet = 1 / float(det)
            ra = e * idet
            rb = -b * idet
            rd = -d * idet
            re = a * idet
            a,b,c,d,e,f = (ra, rb, -c*ra - f*rb, rd, re, -c*rd, f*re)
            self.inv_transform_coeffs = a,b,c,d,e,f
        else:
            raise Exception("Error with the transform matrix")

    def positioned(self, width, height, coordspace_bbox):
        # Get coords of view corners
        xleft, ytop, xright, ybottom = coordspace_bbox
        view_corners = [
            (xleft, ytop), (xleft, ybottom), (xright, ybottom), (xright, ytop)
        ]
        # Get pixel location of view corners
        view_corner_pixels = [self.geo_to_cell(*point, fraction=True) for point in view_corners]

        flattened = [xory for point in view_corner_pixels for xory in point]
        new_raster = self.copy()

        mask = self.mask

        mask_trans = mask.transform(
            (width, height), PIL.Image.QUAD, flattened, resample=PIL.Image.NEAREST
            )

        for band in new_raster.bands:
            data_trans = band.img.transform(
                (width, height), PIL.Image.QUAD, flattened, resample=PIL.Image.NEAREST)
                )
        
            trans = PIL.Image.new(data_trans.mode, data_trans.size)
            trans.paste(datatrans, (0,0), mask_trans)
            # Store image and cells
            band.img = trans
            band.cells = band.img.load()

        return new_raster, mask_trans