import numpy as np
from .baseStacker import BaseStacker
from .generalStackers import SeasonStacker

__all__ = ['wrapRADec', 'wrapRA', 'inHexagon', 'polygonCoords',
           'RandomDitherFieldVisitStacker', 'RandomDitherFieldNightStacker', 'RandomDitherNightStacker',
           'SpiralDitherFieldVisitStacker', 'SpiralDitherFieldNightStacker', 'SpiralDitherNightStacker',
           'HexDitherFieldVisitStacker', 'HexDitherFieldNightStacker', 'HexDitherNightStacker']

# Stacker naming scheme:
# [Pattern]Dither[Field][Timescale].
#  Timescale indicates how often the dither offset is changed.
#  The presence of 'Field' indicates that a new offset is chosen per field, on the indicated timescale.
#  The absence of 'Field' indicates that all visits within the indicated timescale use the same dither offset.


# Original dither stackers (Random, Spiral, Hex) written by Lynne Jones (lynnej@uw.edu)
# Additional dither stackers written by Humna Awan (humna.awan@rutgers.edu), with addition of
# constraining dither offsets to be within an inscribed hexagon (some
# small code modifications for use here by LJ).


def wrapRADec(ra, dec):
    """
    Wrap RA into 0-2pi and Dec into +/0 pi/2.

    Parameters
    ----------
    ra : numpy.ndarray
        RA in radians
    dec : numpy.ndarray
        Dec in radians

    Returns
    -------
    numpy.ndarray, numpy.ndarray
        Wrapped RA/Dec values.
    """
    # Wrap dec.
    low = np.where(dec < -np.pi/2.0)[0]
    dec[low] = -1 * (np.pi + dec[low])
    ra[low] = ra[low] - np.pi
    high = np.where(dec > np.pi/2.0)[0]
    dec[high] = np.pi - dec[high]
    ra[high] = ra[high] - np.pi
    # Wrap RA.
    ra = ra % (2.0*np.pi)
    return ra, dec


def wrapRA(ra):
    """
    Wrap only RA values into 0-2pi (using mod).
    """
    ra = ra % (2.0*np.pi)
    return ra


def inHexagon(xOff, yOff, maxDither):
    """
    Identify dither offsets which fall within the inscribed hexagon.
    """
    # Set up the hexagon limits.
    #  y=mx+b, 2h is the height.
    m = np.sqrt(3.0)
    b = m*maxDither
    h = m/2.0*maxDither
    # Identify offsets inside hexagon.
    inside = np.where((yOff < m*xOff + b) &
                      (yOff > m*xOff - b) &
                      (yOff < -m*xOff + b) &
                      (yOff > -m*xOff - b) &
                      (yOff < h) & (yOff > -h))[0]
    return inside


def polygonCoords(nside, radius, rotationAngle):
    """
    Find the x,y coords of a polygon. (useful for plotting dither points).
    """
    eachAngle = 2*np.pi/nside
    xCoords = np.zeros(nside, float)
    yCoords = np.zeros(nside, float)
    for i in range(0, nside):
        xCoords[i] = np.sin(eachAngle*i + rotationAngle)*radius
        yCoords[i] = np.cos(eachAngle*i + rotationAngle)*radius
    return zip(xCoords, yCoords)


class RandomDitherFieldVisitStacker(BaseStacker):
    """
    Randomly dither the RA and Dec pointings up to maxDither degrees from center, different offset for each field, for each visit.
    Optionally constrain dither offsets to lie within inscribed hexagon of FOV.
    """

    def __init__(self, raCol='fieldRA', decCol='fieldDec', maxDither=1.75,
                 inHex=True, randomSeed=None):
        """
        @ MaxDither in degrees
        """
        # Instantiate the RandomDither object and set internal variables.
        self.raCol = raCol
        self.decCol = decCol
        # Convert maxDither from degrees (internal units for ra/dec are radians)
        self.maxDither = np.radians(maxDither)
        self.inHex = inHex
        self.randomSeed = randomSeed
        # self.units used for plot labels
        self.units = ['rad', 'rad']
        # Values required for framework operation: this specifies the names of the new columns.
        self.colsAdded = ['randomDitherFieldVisitRa', 'randomDitherFieldVisitDec']
        # Values required for framework operation: this specifies the data columns required from the database.
        self.colsReq = [self.raCol, self.decCol]

    def _generateRandomOffsets(self, noffsets):
        xOut = np.array([], float)
        yOut = np.array([], float)
        maxTries = 100
        tries = 0
        while (len(xOut) < noffsets) and (tries < maxTries):
            dithersRad = np.sqrt(np.random.rand(noffsets*2))*self.maxDither
            dithersTheta = np.random.rand(noffsets*2)*np.pi*2.0
            xOff = dithersRad * np.cos(dithersTheta)
            yOff = dithersRad * np.sin(dithersTheta)
            if self.inHex:
                # Constrain dither offsets to be within hexagon.
                idx = inHexagon(xOff, yOff, self.maxDither)
                xOff = xOff[idx]
                yOff = yOff[idx]
            xOut = np.concatenate([xOut, xOff])
            yOut = np.concatenate([yOut, yOff])
            tries += 1
        if len(xOut) < noffsets:
            raise ValueError(
                'Could not find enough random points within the hexagon in %d tries. Try another random seed?' % (maxTries))
        self.xOff = xOut[0:noffsets]
        self.yOff = yOut[0:noffsets]

    def _run(self, simData):
        # Generate random numbers for dither, using defined seed value if desired.
        if self.randomSeed is not None:
            np.random.seed(self.randomSeed)
        # Generate the random dither values.
        noffsets = len(simData[self.raCol])
        self._generateRandomOffsets(noffsets)
        # Add to RA and dec values.
        simData['randomDitherFieldVisitRa'] = simData[self.raCol] + self.xOff/np.cos(simData[self.decCol])
        simData['randomDitherFieldVisitDec'] = simData[self.decCol] + self.yOff
        # Wrap back into expected range.
        simData['randomDitherFieldVisitRa'], simData['randomDitherFieldVisitDec'] = wrapRADec(simData['randomDitherFieldVisitRa'],
                                                                                              simData['randomDitherFieldVisitDec'])
        return simData


class RandomDitherFieldNightStacker(RandomDitherFieldVisitStacker):
    """
    Randomly dither the RA and Dec pointings up to maxDither degrees from center, one dither offset
    per new night of observation of a field (so visits within the same night, to the same field, have the same offset).
    """

    def __init__(self, raCol='fieldRA', decCol='fieldDec', fieldIdCol='fieldID', nightCol='night',
                 maxDither=1.75, inHex=True, randomSeed=None):
        """
        @ MaxDither in degrees
        """
        # Instantiate the RandomDither object and set internal variables.
        super(RandomDitherFieldNightStacker, self).__init__(raCol=raCol, decCol=decCol,
                                                            maxDither=maxDither, inHex=inHex, randomSeed=randomSeed)
        self.nightCol = nightCol
        self.fieldIdCol = fieldIdCol
        # Values required for framework operation: this specifies the names of the new columns.
        self.colsAdded = ['randomDitherFieldNightRa', 'randomDitherFieldNightDec']
        # Values required for framework operation: this specifies the data columns required from the database.
        self.colsReq = [self.raCol, self.decCol, self.nightCol, self.fieldIdCol]

    def _run(self, simData):
        # Generate random numbers for dither, using defined seed value if desired.
        if self.randomSeed is not None:
            np.random.seed(self.randomSeed)
        # Generate the random dither values, one per night per field.
        fields = np.unique(simData[self.fieldIdCol])
        nights = np.unique(simData[self.nightCol])
        self._generateRandomOffsets(len(fields)*len(nights))
        # counter to ensure new random numbers are chosen every time
        delta = 0
        for fieldid in np.unique(simData[self.fieldIdCol]):
            # Identify observations of this field.
            match = np.where(simData[self.fieldIdCol] == fieldid)[0]
            # Apply dithers, increasing each night.
            nights = simData[self.nightCol][match]
            vertexIdxs = np.searchsorted(np.unique(nights), nights)
            vertexIdxs = vertexIdxs % len(self.xOff)
            # ensure that the same xOff/yOff entries are not chosen
            delta = delta + len(vertexIdxs)
            simData['randomDitherFieldNightRa'][match] = simData[self.raCol][
                match] + self.xOff[vertexIdxs]/np.cos(simData[self.decCol][match])
            simData['randomDitherFieldNightDec'][match] = simData[self.decCol][match] + self.yOff[vertexIdxs]
        # Wrap into expected range.
        simData['randomDitherFieldNightRa'], simData['randomDitherFieldNightDec'] = \
            wrapRADec(simData['randomDitherFieldNightRa'], simData['randomDitherFieldNightDec'])
        return simData


class RandomDitherNightStacker(RandomDitherFieldVisitStacker):
    """
    Randomly dither the RA and Dec pointings up to maxDither degrees from center, one dither offset per night.
    All fields observed within the same night get the same offset.
    """

    def __init__(self, raCol='fieldRA', decCol='fieldDec', nightCol='night',
                 maxDither=1.75, inHex=True, randomSeed=None):
        """
        @ MaxDither in degrees
        """
        # Instantiate the RandomDither object and set internal variables.
        super(RandomDitherNightStacker, self).__init__(raCol=raCol, decCol=decCol,
                                                       maxDither=maxDither, inHex=inHex, randomSeed=randomSeed)
        self.nightCol = nightCol
        # Values required for framework operation: this specifies the names of the new columns.
        self.colsAdded = ['randomDitherNightRa', 'randomDitherNightDec']
        # Values required for framework operation: this specifies the data columns required from the database.
        self.colsReq = [self.raCol, self.decCol, self.nightCol]

    def _run(self, simData):
        # Generate random numbers for dither, using defined seed value if desired.
        if self.randomSeed is not None:
            np.random.seed(self.randomSeed)
        # Generate the random dither values, one per night.
        nights = np.unique(simData[self.nightCol])
        self._generateRandomOffsets(len(nights))
        # Add to RA and dec values.
        for n, x, y in zip(nights, self.xOff, self.yOff):
            match = np.where(simData[self.nightCol] == n)[0]
            simData['randomDitherNightRa'][match] = simData[self.raCol][
                match] + x/np.cos(simData[self.decCol][match])
            simData['randomDitherNightDec'][match] = simData[self.decCol][match] + y
        # Wrap RA/Dec into expected range.
        simData['randomDitherNightRa'], simData['randomDitherNightDec'] = wrapRADec(simData['randomDitherNightRa'],
                                                                                    simData['randomDitherNightDec'])
        return simData


class SpiralDitherFieldVisitStacker(BaseStacker):
    """
    Offset along an equidistant spiral with numPoints, out to a maximum radius of maxDither.
    Sequential offset for each individual visit to a field.
    """

    def __init__(self, raCol='fieldRA', decCol='fieldDec', fieldIdCol='fieldID',
                 numPoints=60, maxDither=1.75, nCoils=5, inHex=True):
        """
        @ MaxDither in degrees
        """
        self.raCol = raCol
        self.decCol = decCol
        self.fieldIdCol = fieldIdCol
        # Convert maxDither from degrees (internal units for ra/dec are radians)
        self.numPoints = numPoints
        self.nCoils = nCoils
        self.maxDither = np.radians(maxDither)
        self.inHex = inHex
        # self.units used for plot labels
        self.units = ['rad', 'rad']
        # Values required for framework operation: this specifies the names of the new columns.
        self.colsAdded = ['spiralDitherFieldVisitRa', 'spiralDitherFieldVisitDec']
        # Values required for framework operation: this specifies the data columns required from the database.
        self.colsReq = [self.raCol, self.decCol, self.fieldIdCol]

    def _generateSpiralOffsets(self):
        # First generate a full archimedean spiral ..
        theta = np.arange(0.0001, self.nCoils*np.pi*2., 0.001)
        a = self.maxDither/theta.max()
        if self.inHex:
            a = 0.85 * a
        r = theta*a
        # Then pick out equidistant points along the spiral.
        arc = a / 2.0 * (theta * np.sqrt(1 + theta**2) + np.log(theta + np.sqrt(1 + theta**2)))
        stepsize = arc.max()/float(self.numPoints)
        arcpts = np.arange(0, arc.max(), stepsize)
        arcpts = arcpts[0:self.numPoints]
        rpts = np.zeros(self.numPoints, float)
        thetapts = np.zeros(self.numPoints, float)
        for i, ap in enumerate(arcpts):
            diff = np.abs(arc - ap)
            match = np.where(diff == diff.min())[0]
            rpts[i] = r[match]
            thetapts[i] = theta[match]
        # Translate these r/theta points into x/y (ra/dec) offsets.
        self.xOff = rpts * np.cos(thetapts)
        self.yOff = rpts * np.sin(thetapts)

    def _run(self, simData):
        # Generate the spiral offset vertices.
        self._generateSpiralOffsets()
        # Now apply to observations.
        for fieldid in np.unique(simData[self.fieldIdCol]):
            match = np.where(simData[self.fieldIdCol] == fieldid)[0]
            # Apply sequential dithers, increasing with each visit.
            vertexIdxs = np.arange(0, len(match), 1)
            vertexIdxs = vertexIdxs % self.numPoints
            simData['spiralDitherFieldVisitRa'][match] = simData[self.raCol][match] + \
                self.xOff[vertexIdxs]/np.cos(simData[self.decCol][match])
            simData['spiralDitherFieldVisitDec'][match] = simData[self.decCol][match] + self.yOff[vertexIdxs]
        # Wrap into expected range.
        simData['spiralDitherFieldVisitRa'], simData['spiralDitherFieldVisitDec'] = wrapRADec(simData['spiralDitherFieldVisitRa'],
                                                                                              simData['spiralDitherFieldVisitDec'])
        return simData


class SpiralDitherFieldNightStacker(SpiralDitherFieldVisitStacker):
    """
    Offset along an equidistant spiral with numPoints, out to a maximum radius of maxDither.
    Sequential offset for each night of visits to a field.
    """

    def __init__(self, raCol='fieldRA', decCol='fieldDec', fieldIdCol='fieldID', nightCol='night',
                 numPoints=60, maxDither=1.75, nCoils=5, inHex=True):
        """
        @ MaxDither in degrees
        """
        super(SpiralDitherFieldNightStacker, self).__init__(raCol=raCol, decCol=decCol, fieldIdCol=fieldIdCol,
                                                            numPoints=numPoints, maxDither=maxDither, nCoils=nCoils, inHex=inHex)
        self.nightCol = nightCol
        # Values required for framework operation: this specifies the names of the new columns.
        self.colsAdded = ['spiralDitherFieldNightRa', 'spiralDitherFieldNightDec']
        # Values required for framework operation: this specifies the data columns required from the database.
        self.colsReq.append(self.nightCol)

    def _run(self, simData):
        self._generateSpiralOffsets()
        for fieldid in np.unique(simData[self.fieldIdCol]):
            # Identify observations of this field.
            match = np.where(simData[self.fieldIdCol] == fieldid)[0]
            # Apply a sequential dither, increasing each night.
            nights = simData[self.nightCol][match]
            vertexIdxs = np.searchsorted(np.unique(nights), nights)
            vertexIdxs = vertexIdxs % self.numPoints
            simData['spiralDitherFieldNightRa'][match] = simData[self.raCol][match] + \
                self.xOff[vertexIdxs]/np.cos(simData[self.decCol][match])
            simData['spiralDitherFieldNightDec'][match] = simData[self.decCol][match] + self.yOff[vertexIdxs]
        # Wrap into expected range.
        simData['spiralDitherFieldNightRa'], simData['spiralDitherFieldNightDec'] = wrapRADec(simData['spiralDitherFieldNightRa'],
                                                                                              simData['spiralDitherFieldNightDec'])
        return simData


class SpiralDitherNightStacker(SpiralDitherFieldVisitStacker):
    """
    Offset along an equidistant spiral with numPoints, out to a maximum radius of maxDither.
    Sequential offset per night for all fields.
    """

    def __init__(self, raCol='fieldRA', decCol='fieldDec', fieldIdCol='fieldID', nightCol='night',
                 numPoints=60, maxDither=1.75, nCoils=5, inHex=True):
        """
        @ MaxDither in degrees
        """
        super(SpiralDitherNightStacker, self).__init__(raCol=raCol, decCol=decCol, fieldIdCol=fieldIdCol,
                                                       numPoints=numPoints, maxDither=maxDither, nCoils=nCoils, inHex=inHex)
        self.nightCol = nightCol
        # Values required for framework operation: this specifies the names of the new columns.
        self.colsAdded = ['spiralDitherNightRa', 'spiralDitherNightDec']
        # Values required for framework operation: this specifies the data columns required from the database.
        self.colsReq.append(self.nightCol)

    def _run(self, simData):
        self._generateSpiralOffsets()
        nights = np.unique(simData[self.nightCol])
        # Add to RA and dec values.
        vertexIdxs = np.searchsorted(nights, simData[self.nightCol])
        vertexIdxs = vertexIdxs % self.numPoints
        simData['spiralDitherNightRa'] = simData[self.raCol] + \
            self.xOff[vertexIdxs]/np.cos(simData[self.decCol])
        simData['spiralDitherNightDec'] = simData[self.decCol] + self.yOff[vertexIdxs]
        # Wrap RA/Dec into expected range.
        simData['spiralDitherNightRa'], simData['spiralDitherNightDec'] = \
            wrapRADec(simData['spiralDitherNightRa'], simData['spiralDitherNightDec'])
        return simData


class HexDitherFieldVisitStacker(BaseStacker):
    """
    Use offsets from the hexagonal grid of 'hexdither', but visit each vertex sequentially.
    Sequential offset for each visit.
    """

    def __init__(self, raCol='fieldRA', decCol='fieldDec', fieldIdCol='fieldID', maxDither=1.8, inHex=True):
        """
        @ MaxDither in degrees
        """
        self.raCol = raCol
        self.decCol = decCol
        self.fieldIdCol = fieldIdCol
        self.maxDither = np.radians(maxDither)
        self.inHex = inHex
        # self.units used for plot labels
        self.units = ['rad', 'rad']
        # Values required for framework operation: this specifies the names of the new columns.
        self.colsAdded = ['hexDitherFieldVisitRa', 'hexDitherFieldVisitDec']
        # Values required for framework operation: this specifies the data columns required from the database.
        self.colsReq = [self.raCol, self.decCol, self.fieldIdCol]

    def _generateHexOffsets(self):
        # Set up basics of dither pattern.
        dith_level = 4
        nrows = 2**dith_level
        halfrows = int(nrows/2.)
        # Calculate size of each offset
        dith_size_x = self.maxDither*2.0/float(nrows)
        dith_size_y = np.sqrt(3)*self.maxDither/float(nrows)  # sqrt 3 comes from hexagon
        if self.inHex:
            dith_size_x = 0.95 * dith_size_x
            dith_size_y = 0.95 * dith_size_y
        # Calculate the row identification number, going from 0 at center
        nid_row = np.arange(-halfrows, halfrows+1, 1)
        # and calculate the number of vertices in each row.
        vert_in_row = np.arange(-halfrows, halfrows+1, 1)
        # First calculate how many vertices we will create in each row.
        total_vert = 0
        for i in range(-halfrows, halfrows+1, 1):
            vert_in_row[i] = (nrows+1) - abs(nid_row[i])
            total_vert += vert_in_row[i]
        self.numPoints = total_vert
        self.xOff = []
        self.yOff = []
        # Calculate offsets over hexagonal grid.
        for i in range(0, nrows+1, 1):
            for j in range(0, vert_in_row[i], 1):
                self.xOff.append(dith_size_x * (j - (vert_in_row[i]-1)/2.0))
                self.yOff.append(dith_size_y * nid_row[i])
        self.xOff = np.array(self.xOff)
        self.yOff = np.array(self.yOff)

    def _run(self, simData):
        self._generateHexOffsets()
        for fieldid in np.unique(simData[self.fieldIdCol]):
            # Identify observations of this field.
            match = np.where(simData[self.fieldIdCol] == fieldid)[0]
            # Apply sequential dithers, increasing with each visit.
            vertexIdxs = np.arange(0, len(match), 1)
            vertexIdxs = vertexIdxs % self.numPoints
            simData['hexDitherFieldVisitRa'][match] = simData[self.raCol][match] + \
                self.xOff[vertexIdxs]/np.cos(simData[self.decCol][match])
            simData['hexDitherFieldVisitDec'][match] = simData[self.decCol][match] + self.yOff[vertexIdxs]
        # Wrap into expected range.
        simData['hexDitherFieldVisitRa'], simData['hexDitherFieldVisitDec'] = wrapRADec(simData['hexDitherFieldVisitRa'],
                                                                                        simData['hexDitherFieldVisitDec'])
        return simData


class HexDitherFieldNightStacker(HexDitherFieldVisitStacker):
    """
    Use offsets from the hexagonal grid of 'hexdither', but visit each vertex sequentially.
    Sequential offset for each night of visits.
    """

    def __init__(self, raCol='fieldRA', decCol='fieldDec', fieldIdCol='fieldIdCol', nightCol='night', maxDither=1.8, inHex=True):
        """
        @ MaxDither in degrees
        """
        super(HexDitherFieldNightStacker, self).__init__(
            raCol=raCol, decCol=decCol, maxDither=maxDither, inHex=inHex)
        self.nightCol = nightCol
        # Values required for framework operation: this specifies the names of the new columns.
        self.colsAdded = ['hexDitherFieldNightRa', 'hexDitherFieldNightDec']
        # Values required for framework operation: this specifies the data columns required from the database.
        self.colsReq.append(self.nightCol)

    def _run(self, simData):
        self._generateHexOffsets()
        for fieldid in np.unique(simData[self.fieldIdCol]):
            # Identify observations of this field.
            match = np.where(simData[self.fieldIdCol] == fieldid)[0]
            # Apply a sequential dither, increasing each night.
            vertexIdxs = np.arange(0, len(match), 1)
            nights = simData[self.nightCol][match]
            vertexIdxs = np.searchsorted(np.unique(nights), nights)
            vertexIdxs = vertexIdxs % self.numPoints
            simData['hexDitherFieldNightRa'][match] = simData[self.raCol][match] + \
                self.xOff[vertexIdxs]/np.cos(simData[self.decCol][match])
            simData['hexDitherFieldNightDec'][match] = simData[self.decCol][match] + self.yOff[vertexIdxs]
        # Wrap into expected range.
        simData['hexDitherFieldNightRa'], simData['hexDitherFieldNightDec'] = \
            wrapRADec(simData['hexDitherFieldNightRa'], simData['hexDitherFieldNightDec'])
        return simData


class HexDitherNightStacker(HexDitherFieldVisitStacker):
    """
    Use offsets from the hexagonal grid of 'hexdither', but visit each vertex sequentially.
    Sequential offset per night for all fields.
    """

    def __init__(self, raCol='fieldRA', decCol='fieldDec', fieldIdCol='fieldID', nightCol='night', maxDither=1.75, inHex=True):
        """
        @ MaxDither in degrees
        """
        super(HexDitherNightStacker, self).__init__(raCol=raCol, decCol=decCol, fieldIdCol=fieldIdCol,
                                                    maxDither=maxDither, inHex=inHex)
        self.nightCol = nightCol
        # Values required for framework operation: this specifies the names of the new columns.
        self.colsAdded = ['hexDitherNightRa', 'hexDitherNightDec']
        # Values required for framework operation: this specifies the data columns required from the database.
        self.colsReq.append(self.nightCol)

    def _run(self, simData):
        # Generate the spiral dither values
        self._generateHexOffsets()
        nights = np.unique(simData[self.nightCol])
        # Add to RA and dec values.
        vertexID = 0
        for n in nights:
            match = np.where(simData[self.nightCol] == n)[0]
            vertexID = vertexID % self.numPoints
            simData['hexDitherNightRa'][match] = simData[self.raCol][match] + \
                self.xOff[vertexID]/np.cos(simData[self.decCol][match])
            simData['hexDitherNightDec'][match] = simData[self.decCol][match] + self.yOff[vertexID]
            vertexID += 1
        # Wrap RA/Dec into expected range.
        simData['hexDitherNightRa'], simData['hexDitherNightDec'] = \
            wrapRADec(simData['hexDitherNightRa'], simData['hexDitherNightDec'])
        return simData
